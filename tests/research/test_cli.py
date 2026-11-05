from qa_framework.research.cli import main
import sys

def test_cli_verify_valid_trace(capsys):
    import json
    trace = ["brief_exists", "dispatch", "validation_passed", "report"]
    with open("/tmp/test_trace.json", "w") as f:
        json.dump(trace, f)
    
    sys.argv = ["cli.py", "verify", "/tmp/test_trace.json"]
    main()
    captured = capsys.readouterr()
    assert "valid" in captured.out.lower()

def test_cli_verify_invalid_trace(capsys):
    import json
    trace = ["dispatch", "report"]
    with open("/tmp/test_trace.json", "w") as f:
        json.dump(trace, f)
    
    sys.argv = ["cli.py", "verify", "/tmp/test_trace.json"]
    main()
    captured = capsys.readouterr()
    assert "invalid" in captured.out.lower() or "violated" in captured.out.lower()
