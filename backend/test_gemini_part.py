import google.generativeai as genai
from google.generativeai.types import content_types

print([field.name for field in genai.protos.Part.DESCRIPTOR.fields])
