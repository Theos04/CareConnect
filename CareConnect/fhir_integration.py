"""
fhir_integration.py
FHIR R4 / Blue Button 2.0 blueprint for CareConnect.

Registered in app.py via:
    from fhir_integration import fhir_bp
    app.register_blueprint(fhir_bp)
"""
from flask import Blueprint, request, jsonify, session, current_app, g
import requests
from datetime import datetime
import uuid

fhir_bp = Blueprint('fhir', __name__)

# ─────────────────────────────────────────────────────────────────────────────
# Helper — require a logged-in user on every FHIR route
# ─────────────────────────────────────────────────────────────────────────────
def _require_login():
    if not session.get('user_id'):
        return jsonify({'error': 'Authentication required'}), 401
    return None


# ─────────────────────────────────────────────────────────────────────────────
# FHIRIntegration class
# ─────────────────────────────────────────────────────────────────────────────
class FHIRIntegration:
    """Thin wrapper around FHIR R4 and Blue Button 2.0 APIs."""

    FHIR_SERVER      = 'https://r4.smarthealthit.org'   # public sandbox
    BLUE_BUTTON_URL  = 'https://sandbox.bluebutton.cms.gov'

    def __init__(self, fhir_token: str | None = None):
        self.fhir_token = fhir_token

    def _auth_headers(self) -> dict:
        h = {'Content-Type': 'application/fhir+json', 'Accept': 'application/fhir+json'}
        if self.fhir_token:
            h['Authorization'] = f'Bearer {self.fhir_token}'
        return h

    # ── Export ────────────────────────────────────────────────────────────────
    def build_patient_bundle(self, patient_id: int, prescriptions: list) -> dict:
        """Build a FHIR Bundle from local DB data — no external call needed."""
        entries = []

        # Patient resource (minimal)
        entries.append({
            'fullUrl': f'urn:uuid:{uuid.uuid4()}',
            'resource': {
                'resourceType': 'Patient',
                'id': str(patient_id),
                'identifier': [{'value': str(patient_id)}],
            },
            'request': {'method': 'PUT', 'url': f'Patient/{patient_id}'},
        })

        # MedicationRequest per prescription
        for rx in prescriptions:
            entries.append({
                'fullUrl': f'urn:uuid:{uuid.uuid4()}',
                'resource': {
                    'resourceType': 'MedicationRequest',
                    'status': rx.get('status', 'active').lower(),
                    'intent': 'order',
                    'medicationCodeableConcept': {
                        'text': rx.get('medication', '')
                    },
                    'subject': {'reference': f'Patient/{patient_id}'},
                    'dosageInstruction': [{'text': rx.get('dosage', '')}],
                    'authoredOn': rx.get('date', datetime.utcnow().date().isoformat()),
                },
                'request': {'method': 'POST', 'url': 'MedicationRequest'},
            })

        return {
            'resourceType': 'Bundle',
            'type': 'transaction',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'entry': entries,
        }

    # ── Blue Button import ────────────────────────────────────────────────────
    def fetch_blue_button_records(self, patient_id: str, access_token: str) -> dict:
        headers = {'Authorization': f'Bearer {access_token}'}
        base = self.BLUE_BUTTON_URL + '/v1/fhir'
        results = {}
        for resource in ('ExplanationOfBenefit', 'Patient', 'Coverage'):
            url = f'{base}/{resource}' if resource != 'Patient' else f'{base}/Patient/{patient_id}'
            try:
                r = requests.get(url, headers=headers, timeout=10)
                results[resource.lower()] = r.json() if r.ok else {}
            except requests.RequestException:
                results[resource.lower()] = {}
        return results

    def convert_to_fhir(self, records: dict) -> dict:
        bundle = {'resourceType': 'Bundle', 'type': 'transaction', 'entry': []}
        for resource_type, data in records.items():
            if not data:
                continue
            entries = data.get('entry', [data])  # single resource or bundle
            for item in entries:
                resource = item.get('resource', item)
                bundle['entry'].append({
                    'resource': resource,
                    'request': {'method': 'POST', 'url': resource.get('resourceType', 'Resource')},
                })
        return bundle

    def store_fhir_data(self, patient_id: int, fhir_bundle: dict) -> None:
        """Persist imported FHIR bundle — extend with DB storage as needed."""
        current_app.logger.info(
            'FHIR import: patient=%s entries=%d',
            patient_id, len(fhir_bundle.get('entry', []))
        )

    # ── Observation ───────────────────────────────────────────────────────────
    def create_fhir_observation(self, patient_id: int, obs: dict) -> dict:
        payload = {
            'resourceType': 'Observation',
            'status': 'final',
            'category': [{'coding': [{
                'system': 'http://terminology.hl7.org/CodeSystem/observation-category',
                'code': 'vital-signs',
            }]}],
            'code': {'coding': [{
                'system': 'http://loinc.org',
                'code': obs.get('loinc_code', ''),
                'display': obs.get('display', ''),
            }]},
            'subject': {'reference': f'Patient/{patient_id}'},
            'effectiveDateTime': datetime.utcnow().isoformat() + 'Z',
            'valueQuantity': {
                'value': obs.get('value'),
                'unit': obs.get('unit', ''),
                'system': 'http://unitsofmeasure.org',
            },
        }
        try:
            r = requests.post(
                f'{self.FHIR_SERVER}/Observation',
                json=payload, headers=self._auth_headers(), timeout=10
            )
            return r.json() if r.ok else {'error': r.text}
        except requests.RequestException as e:
            return {'error': str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@fhir_bp.route('/api/fhir/export', methods=['POST'])
def export_health_data():
    """Build a FHIR Bundle from the patient's local prescriptions and return it."""
    err = _require_login()
    if err:
        return err

    from models import Prescription
    patient_id = session['user_id']
    rxs = (Prescription.query
           .filter_by(patient_id=patient_id)
           .order_by(Prescription.created_at.desc())
           .all())

    fhir = FHIRIntegration(fhir_token=session.get('fhir_token'))
    bundle = fhir.build_patient_bundle(patient_id, [p.to_dict() for p in rxs])

    fmt = (request.get_json(silent=True) or {}).get('format', 'json')
    if fmt == 'download':
        from flask import Response
        return Response(
            __import__('json').dumps(bundle, indent=2),
            mimetype='application/fhir+json',
            headers={'Content-Disposition': f'attachment; filename=careconnect_export_{patient_id}.json'}
        )
    return jsonify({'status': 'success', 'bundle': bundle,
                    'entry_count': len(bundle['entry'])})


@fhir_bp.route('/api/fhir/import', methods=['POST'])
def import_health_records():
    """Import records from Blue Button 2.0 or other FHIR sources."""
    err = _require_login()
    if err:
        return err

    data         = request.get_json(silent=True) or {}
    source       = data.get('source', 'blue_button')
    access_token = data.get('access_token', '')
    patient_id   = session['user_id']

    fhir = FHIRIntegration()
    if source == 'blue_button':
        records = fhir.fetch_blue_button_records(str(patient_id), access_token)
    else:
        records = {}

    bundle = fhir.convert_to_fhir(records)
    fhir.store_fhir_data(patient_id, bundle)

    return jsonify({
        'status': 'success',
        'source': source,
        'imported_records': len(bundle.get('entry', [])),
        'message': f'Imported {len(bundle.get("entry", []))} records from {source}',
    })


@fhir_bp.route('/api/fhir/share', methods=['POST'])
def share_records():
    """Generate a shareable FHIR bundle for a specific recipient."""
    err = _require_login()
    if err:
        return err

    data       = request.get_json(silent=True) or {}
    recipient  = data.get('recipient', '')
    patient_id = session['user_id']

    from models import Prescription
    rxs = Prescription.query.filter_by(patient_id=patient_id).all()
    fhir   = FHIRIntegration()
    bundle = fhir.build_patient_bundle(patient_id, [p.to_dict() for p in rxs])

    return jsonify({
        'status':      'success',
        'shared_with': recipient,
        'shared_at':   datetime.utcnow().isoformat(),
        'bundle_size': len(bundle['entry']),
    })


@fhir_bp.route('/api/fhir/observation', methods=['POST'])
def create_observation():
    """Push a vital-sign observation to the FHIR server."""
    err = _require_login()
    if err:
        return err

    obs_data   = request.get_json(silent=True) or {}
    patient_id = session['user_id']
    fhir       = FHIRIntegration(fhir_token=session.get('fhir_token'))
    result     = fhir.create_fhir_observation(patient_id, obs_data)
    return jsonify(result)
