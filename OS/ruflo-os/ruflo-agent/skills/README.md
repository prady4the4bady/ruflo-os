# Ruflo Agent Skills

This directory contains skill definitions that the Ruflo Agent can use to perform specialized tasks.

## Skill Format

Skills are defined in `.skill` YAML files with the following structure:

```yaml
name: skill_name
description: What the skill does
trigger_phrases:
  - "phrase 1"
  - "phrase 2"
steps:
  - step 1 description
  - step 2 description
required_tools:
  - tool1
  - tool2
```

## Available Skills

- `web_research.skill` - Research topics on the web
- `code_execution.skill` - Write and run code
- `email_management.skill` - Manage emails
- `file_organization.skill` - Organize files

## Adding New Skills

1. Create a new `.skill` file in this directory
2. Define the skill structure as above
3. The agent will automatically discover and use it when trigger phrases match