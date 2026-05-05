# Contributing to Ruflo OS

## Development Environment Setup
1. Clone the repo: `git clone https://github.com/prady4the4bady/ruflo-os.git`
2. Run setup: `./scripts/setup-dev.sh`
3. Start the stack: `./scripts/run-ruflo.sh`

## Coding Standards
- **Python**: Type hints everywhere, Pydantic v2 models, asyncio, structlog logging, pytest tests
- **C**: Follow Linux kernel coding style for kernel modules
- **Swift**: Follow Apple SwiftUI conventions for UI components
- **Shell**: Use bash with `set -e`, comments for complex logic

## File Organization
- Keep files focused (<400 lines preferred)
- One concern per module
- Clear import boundaries between services
- Each subsystem is independently deployable

## Testing
- Every module must have tests
- Run `make test` from root
- Per-service: `cd <service> && python -m pytest tests/ -v`
- All tests must pass before merging

## Security Rules
1. Agents NEVER access secrets directly - only via broker-issued opaque handles
2. Destructive actions require explicit user approval
3. Sandbox workers run as non-root
4. All external actions are auditable
5. Default policy is deny-all
6. Prompt injection resistance in all LLM-facing components

## Pull Request Process
1. Fork the repo
2. Create a feature branch
3. Commit changes with clear messages
4. Ensure all tests pass
5. Submit PR with description of changes