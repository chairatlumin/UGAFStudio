# Steam QA

List installed games and find the Steam App ID:

```powershell
python -m qa_framework.steam_cli list
```

Then run QA against a game:

```powershell
python -m qa_framework.steam_qa --app-id 123456
```

Use `--steam-root` when Steam is installed outside the default Windows paths.
