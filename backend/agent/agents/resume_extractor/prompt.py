
validation_system_prompt = (
    "You are a helpful assistant that validates the extracted resume profile. " \
    "Your only task is to determine if the resume profile contains amount of garbled text or other forms of corruption. " \
    "Please validate the extracted resume profile and return whether it's valid or not, along with the reason for the validation result." \
    "Here follows the extracted resume profile that needs to be validated: "
)

section_extraction_system_prompt = (
    # TODO: improve this prompt with more instructions
)

facts_extraction_system_prompt = (
    # TODO: improve this prompt with more instructions
)

__all__ = [
    "validation_system_prompt",
    "section_extraction_system_prompt",
    "facts_extraction_system_prompt"
]