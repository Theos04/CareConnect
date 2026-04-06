# fhir_transformer.py

class FHIRTransformer:
    """
    A class to transform CareConnect models into FHIR resources.
    """
    def __init__(self):
        pass

    def transform_patient(self, careconnect_patient):
        # Transform CareConnect patient model to FHIR Patient resource
        fhir_patient = {
            'resourceType': 'Patient',
            'id': careconnect_patient['id'],
            'name': [{'family': careconnect_patient['lastName'], 'given': [careconnect_patient['firstName']]}],
            'gender': careconnect_patient['gender'],
            'birthDate': careconnect_patient['birthDate'],
            # Add further mapping as required
        }
        return fhir_patient

    def transform_appointment(self, careconnect_appointment):
        # Transform CareConnect appointment model to FHIR Appointment resource
        fhir_appointment = {
            'resourceType': 'Appointment',
            'id': careconnect_appointment['id'],
            'status': careconnect_appointment['status'],
            'start': careconnect_appointment['start'],
            'end': careconnect_appointment['end'],
            # Add further mapping as required
        }
        return fhir_appointment

    def transform_prescription(self, careconnect_prescription):
        # Transform CareConnect prescription model to FHIR MedicationRequest resource
        fhir_prescription = {
            'resourceType': 'MedicationRequest',
            'id': careconnect_prescription['id'],
            'status': careconnect_prescription['status'],
            'medicationCodeableConcept': {
                'text': careconnect_prescription['medication']
            },
            # Add further mapping as required
        }
        return fhir_prescription

    def transform_lab_order(self, careconnect_lab_order):
        # Transform CareConnect lab order model to FHIR DiagnosticOrder resource
        fhir_lab_order = {
            'resourceType': 'DiagnosticOrder',
            'id': careconnect_lab_order['id'],
            'status': careconnect_lab_order['status'],
            # Add further mapping as required
        }
        return fhir_lab_order


class FHIRParser:
    """
    A class to parse FHIR resources back into CareConnect models.
    """
    def __init__(self):
        pass

    def parse_patient(self, fhir_patient):
        # Parse FHIR Patient resource to CareConnect patient model
        careconnect_patient = {
            'id': fhir_patient['id'],
            'firstName': fhir_patient['name'][0]['given'][0],
            'lastName': fhir_patient['name'][0]['family'],
            'gender': fhir_patient['gender'],
            'birthDate': fhir_patient['birthDate'],
            # Add further mapping as required
        }
        return careconnect_patient

    def parse_appointment(self, fhir_appointment):
        # Parse FHIR Appointment resource to CareConnect appointment model
        careconnect_appointment = {
            'id': fhir_appointment['id'],
            'status': fhir_appointment['status'],
            'start': fhir_appointment['start'],
            'end': fhir_appointment['end'],
            # Add further mapping as required
        }
        return careconnect_appointment

    def parse_prescription(self, fhir_prescription):
        # Parse FHIR MedicationRequest resource to CareConnect prescription model
        careconnect_prescription = {
            'id': fhir_prescription['id'],
            'status': fhir_prescription['status'],
            'medication': fhir_prescription['medicationCodeableConcept']['text'],
            # Add further mapping as required
        }
        return careconnect_prescription

    def parse_lab_order(self, fhir_lab_order):
        # Parse FHIR DiagnosticOrder resource to CareConnect lab order model
        careconnect_lab_order = {
            'id': fhir_lab_order['id'],
            'status': fhir_lab_order['status'],
            # Add further mapping as required
        }
        return careconnect_lab_order
