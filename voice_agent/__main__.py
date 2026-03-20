"""Entry point when running as python -m agent."""

from dotenv import load_dotenv

# Load environment variables before importing anything else
load_dotenv()

from .startup import main

if __name__ == "__main__":
    main()
