#Reads all the dynamic fields from the pdf and prints them. Used to reverse engineer the forms.

from PyPDF2 import PdfReader

reader = PdfReader("departure-template.pdf")
fields = reader.get_fields()
for field_name, field_info in fields.items():
    print(field_name, field_info)