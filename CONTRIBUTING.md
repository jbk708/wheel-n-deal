# Contributing to Wheel-n-Deal

Thank you for your interest in contributing to Wheel-n-Deal! This document provides guidelines and instructions for contributing to this project.

## Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct. Please be respectful and considerate of others.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/your-username/wheel-n-deal.git`
3. Set up the development environment:
   ```bash
   cd wheel-n-deal
   ./setup_dev.sh
   ```
4. Create a new branch for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

1. Make your changes
2. Run the linter and formatter:
   ```bash
   ruff check .
   ruff format .
   ```
3. Run tests:
   ```bash
   pytest
   ```
4. Commit your changes with a descriptive commit message:
   ```bash
   git commit -m "Add feature: your feature description"
   ```
5. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
6. Create a Pull Request from your fork to the main repository

## Code Style Guidelines

We use Ruff for linting and formatting. The configuration is in the `pyproject.toml` file. Some key points:

- Line length: 100 characters
- Use double quotes for strings
- Follow PEP 8 naming conventions
- Use type hints where appropriate
- Write docstrings for functions and classes

## Testing

- Write tests for new features and bug fixes
- Ensure all tests pass before submitting a PR
- Aim for good test coverage

## Documentation

- Update documentation for new features
- Keep the README up to date
- Add comments to complex code sections

## Pull Request Process

1. Ensure your code passes all tests and linting
2. Update documentation if necessary
3. Fill out the PR template completely
4. Request a review from a maintainer
5. Address any feedback from reviewers

## Reporting Bugs

- Use the bug report template
- Include steps to reproduce
- Provide information about your environment
- Include screenshots if applicable

## Feature Requests

- Use the feature request template
- Clearly describe the problem and solution
- Consider alternatives you've explored

Thank you for contributing to Wheel-n-Deal! 