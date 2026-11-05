# Studio Framework and ComfyUI

The Studio Framework tab keeps game profiles separate in `data/qa_profiles`. Pick a
genre when creating a profile, choose a screenshot, and enter a scene, chapter,
or level ID. Image analysis runs local OCR and stores its observation and image
path as evidence. A non-empty expected phrase also creates a pass/fail feedback
record. Scene IDs become ordered timeline nodes for that game's profile.

To add a ComfyUI image workflow:

1. Start ComfyUI at `http://127.0.0.1:8188` (or enter another local URL).
2. Build an API-format workflow that contains a `LoadImage` node and the image
   analysis nodes/models you want to use. Studio includes `ใช้ Workflow ตัวอย่าง
   SDXL` for a local image-to-image visual reference workflow; it requires
   `sd_xl_base_1.0.safetensors` in ComfyUI's `models/checkpoints` folder.
3. Save the workflow in API format, then select its JSON in Studio Framework.
4. Select a game and screenshot, then run the ComfyUI workflow. The app waits in
   the background and saves the returned node outputs as game-scoped evidence.

ComfyUI does not include image-generation or vision models with this project.
Install the model and custom nodes required by your chosen workflow. Local OCR
remains available independently when Tesseract is installed. Generated
image-to-image references are creative review artifacts; they do not preserve
subtitle text reliably and never count as testcase PASS evidence. The built-in
workflow is registered only after the user selects it and explicitly reviews
and registers its contents.

Supported profile labels are FMV / Interactive Story, Visual Novel, RPG / JRPG,
Action / Adventure, Platformer, Puzzle, Strategy / Simulation, Horror / Survival,
Racing / Sports, and Other. These labels organize data; each genre still needs
its own authored test steps or a suitable ComfyUI workflow for genre-specific QA.
