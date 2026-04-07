# fhir_integration.py
from flask import Blueprint, request, jsonify, session
import requests
from datetime import datetime
import json

fhir_bp = Blueprint('fhir', __name__)

class FHIRIntegration:
    def __init__(self):
        self.fhir_server = "https://api.logicmonitor.com/fhir"
        self.blue_button_url = "https://bluebutton.cms.gov"
        
    def export_patient_data(self, patient_id, export_format='application/fhir+json'):
        """Export patient data in FHIR format"""
        endpoint = f"{self.fhir_server}/Patient/{patient_id}/$export"
        headers = {
            'Accept': export_format,
            'Authorization': f'Bearer {session.get("fhir_token")}',
            'Prefer': 'respond-async'
        }
        
        response = requests.get(endpoint, headers=headers)
        return response.json()
    
    def import_external_records(self, patient_id, external_source, access_token):
        """Import health records from external sources (Blue Button, Apple Health, etc.)"""
        if external_source == 'blue_button':
            records = self.fetch_blue_button_records(patient_id, access_token)
        elif external_source == 'apple_health':
            records = self.fetch_apple_health_records(access_token)
        elif external_source == 'google_fit':
            records = self.fetch_google_fit_records(access_token)
        
        # Convert to FHIR format and store
        fhir_bundle = self.convert_to_fhir(records)
        self.store_fhir_data(patient_id, fhir_bundle)
        return fhir_bundle
    
    def fetch_blue_button_records(self, patient_id, access_token):
        """Fetch Medicare/Medicaid records from Blue Button API"""
        headers = {'Authorization': f'Bearer {access_token}'}
        
        # Fetch ExplanationOfBenefit (claims) data
        claims_endpoint = f"{self.blue_button_url}/v1/fhir/ExplanationOfBenefit"
        claims_response = requests.get(claims_endpoint, headers=headers)
        
        # Fetch Patient data
        patient_endpoint = f"{self.blue_button_url}/v1/fhir/Patient/{patient_id}"
        patient_response = requests.get(patient_endpoint, headers=headers)
        
        # Fetch Condition data
        conditions_endpoint = f"{self.blue_button_url}/v1/fhir/Condition"
        conditions_response = requests.get(conditions_endpoint, headers=headers)
        
        return {
            'claims': claims_response.json(),
            'patient': patient_response.json(),
            'conditions': conditions_response.json()
        }
    
    def convert_to_fhir(self, records):
        """Convert external records to FHIR format"""
        fhir_bundle = {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": []
        }
        
        # Add patient record
        if 'patient' in records:
            fhir_bundle['entry'].append({
                "resource": records['patient'],
                "request": {"method": "PUT", "url": f"Patient/{records['patient']['id']}"}
            })
        
        # Add conditions
        if 'conditions' in records:
            for condition in records['conditions'].get('entry', []):
                fhir_bundle['entry'].append({
                    "resource": condition['resource'],
                    "request": {"method": "POST", "url": "Condition"}
                })
        
        return fhir_bundle
    
    def store_fhir_data(self, patient_id, fhir_bundle):
        """Store FHIR data in local database"""
        # Implementation for storing FHIR resources
        pass
    
    def get_medication_statement(self, patient_id):
        """Retrieve medication statements in FHIR format"""
        endpoint = f"{self.fhir_server}/MedicationStatement?patient={patient_id}"
        response = requests.get(endpoint)
        return response.json()
    
    def create_fhir_observation(self, patient_id, observation_data):
        """Create a FHIR Observation resource"""
        observation = {
            "resourceType": "Observation",
            "status": "final",
            "category": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                    "code": "vital-signs"
                }]
            }],
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": observation_data['loinc_code'],
                    "display": observation_data['display']
                }]
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": datetime.now().isoformat(),
            "valueQuantity": {
                "value": observation_data['value'],
                "unit": observation_data['unit'],
                "system": "http://unitsofmeasure.org"
            }
        }
        
        response = requests.post(f"{self.fhir_server}/Observation", 
                                json=observation,
                                headers={'Authorization': f'Bearer {session.get("fhir_token")}'})
        return response.json()

# Routes
@fhir_bp.route('/api/fhir/export', methods=['POST'])
def export_health_data():
    """Export patient health data in FHIR/Blue Button format"""
    patient_id = session.get('user_id')
    format_type = request.json.get('format', 'application/fhir+json')
    
    fhir = FHIRIntegration()
    export_data = fhir.export_patient_data(patient_id, format_type)
    
    return jsonify({
        'status': 'success',
        'data': export_data,
        'download_url': f'/api/fhir/download/{export_data.get("job_id")}'
    })

@fhir_bp.route('/api/fhir/import', methods=['POST'])
def import_health_records():
    """Import health records from external sources"""
    patient_id = session.get('user_id')
    source = request.json.get('source')  # 'blue_button', 'apple_health', 'google_fit'
    access_token = request.json.get('access_token')
    
    fhir = FHIRIntegration()
    imported_data = fhir.import_external_records(patient_id, source, access_token)
    
    return jsonify({
        'status': 'success',
        'imported_records': len(imported_data.get('entry', [])),
        'message': f'Successfully imported records from {source}'
    })

@fhir_bp.route('/api/fhir/share', methods=['POST'])
def share_records():
    """Share health records with another provider/institution"""
    patient_id = session.get('user_id')
    recipient = request.json.get('recipient')
    record_types = request.json.get('record_types', ['medications', 'conditions', 'allergies'])
    
    # Generate FHIR document for sharing
    fhir = FHIRIntegration()
    share_document = fhir.export_patient_data(patient_id)
    
    # Send to recipient via secure FHIR endpoint
    # Implementation for SMART on FHIR sharing
    
    return jsonify({
        'status': 'success',
        'shared_with': recipient,
        'shared_at': datetime.now().isoformat()
    })