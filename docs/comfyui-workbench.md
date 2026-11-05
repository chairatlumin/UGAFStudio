# ComfyUI Workbench

The Studio Framework image panel uses local Tesseract for deterministic text checks and can optionally send a screenshot to a developer-managed ComfyUI server for mockup/annotation/review workflows.

## Register and run a workflow

1. Start ComfyUI with its local API on `http://127.0.0.1:8188`.
2. In Studio Framework, choose the game profile, screenshot and ComfyUI API-format workflow JSON.
3. Select a purpose (`UI Mockup`, `Screen Annotation`, or `Visual Review`) and click **ตรวจและลงทะเบียน Workflow ที่ตรวจทานแล้ว**. Inspect the workflow yourself before this step; registration pins the file's SHA-256 hash and node classes in `data/comfyui/workflow_registry.json`.
4. Click the ComfyUI analysis action. It rejects a changed or unregistered file, malformed graph, missing `LoadImage`, missing screenshot, or screenshot above 50 MiB before uploading.
5. Generated image outputs are downloaded from the local ComfyUI server into `reports/comfyui/<profile>/<prompt-id>/`. The Studio evidence record stores each output path, byte count, content type, source workflow hash, and SHA-256; output images over 50 MiB, invalid images, unsafe filenames, and path traversal are rejected.

The bundled `ugaf_ta_optimize_mockup_api.json` workflow turns a synthetic Unreal performance graph into a visual design reference. In Studio Framework, click **ใช้ Workflow ตัวอย่าง TA Optimize Mockup**, review/register the copied workflow, select a graph screenshot, then run it. Diffusion output can distort text and controls; treat it as a palette/layout concept until a developer implements and reviews the real UI. Every ComfyUI result remains `UNASSERTED` and cannot pass a testcase by itself.

Registration is a local trust decision. ComfyUI custom nodes execute in the ComfyUI process, so only register workflows and node packs you trust. A changed workflow must be reviewed and registered again.

## Boundaries and evidence

The service accepts only local HTTP endpoints (`127.0.0.1`, `localhost`, or `::1`); it rejects remote hosts, HTTPS, URL paths, and embedded credentials. ComfyUI failure does not block the local OCR action. Screenshot uploads are sent to the user's local ComfyUI instance; no remote fallback is configured.

Completed workflow metadata (profile, scene, registered workflow hash/purpose, prompt ID, downloaded artifact paths and hashes) is written into the profile's story-evidence database. It is evidence for review, not an automatic testcase PASS. This first slice does not install a ComfyUI server/model pack and does not convert arbitrary workflow output into structured Story Timeline nodes; those remain future integrations.
