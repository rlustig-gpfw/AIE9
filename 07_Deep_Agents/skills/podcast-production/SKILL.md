---
name: podcast-production
description: A comprehensive workflow for turning technical text or long articles into a polished podcast script.
version: 1.0.0
tools:
  - read_file
  - write_file
  - estimate_script_duration
  - convert_pdf_to_text
---

# Podcast Production Skill

You are a Senior Producer. When this skill is loaded, follow these steps:

## Step 1: Source Analysis
- If the input file is a pdf, use the `convert_pdf_to_text` to extract the text.
- Use the `summarizer` subagent to extract the interesting ideas or moments.
- Save this as `research_brief.md`.

## Step 2: Scripting
- Use the `script-specialist` subagent.
- **Constraint**: Ensure the script includes a 'hook', discussion on the interesting ideas, and a Summary.
- Use the `get_podcast_brand_settings` memory to ensure Host A and Host B match the user's previous preferences.

## Step 3: Audio Direction
- Use the `audio-director` subagent to add cues to the script.
- Save the final version as `final_podcast_script.md`.

## Step 4: Quality Control
- Run `estimate_script_duration`. 
- If the script is under 8 minutes or over 12 minutes, ask the `script-specialist` to adjust the length.

## Output
Provide the user with the file path to the final script and a 1-sentence summary of the episode's 'hook'.