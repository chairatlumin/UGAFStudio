# qa_framework/research/cli.py
import sys
import json
from qa_framework.research.verifier import ResearchVerifier

def main():
    if len(sys.argv) < 3:
        print("Usage: cli.py <command> <args>")
        return 2
    
    command = sys.argv[1]
    
    if command == "verify":
        trace_file = sys.argv[2]
        with open(trace_file, 'r') as f:
            trace = json.load(f)
        
        verifier = ResearchVerifier()
        result = verifier.verify(trace)
        if result.valid:
            print("Trace is valid")
            return 0
        else:
            print(f"Trace is invalid: {result.message}")
            return 1
    else:
        print(f"Unknown command: {command}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
