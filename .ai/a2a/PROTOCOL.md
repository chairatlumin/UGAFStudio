# A2A Protocol: Hermes (Planner) ↔ OpenCode (Engineer)

## Roles
- **Hermes** = Planner/Reviewer: ออกแบบงาน, แตก task, เขียน brief, ตรวจผลจริง (re-verify), อัปเดต RESULT.md
- **OpenCode** = Engineer: อ่าน brief, เขียนโค้ด, รัน validation ที่กำหนดใน brief เอง, สรุปผล

## Message format = files (file-based A2A)
- Brief (Hermes → OpenCode): `.ai/a2a/tasks/TASK-<id>.md`
  - ต้องมี: Goal, Context (ไฟล์ที่เกี่ยว), Constraints, Acceptance criteria, Exact validation command
- Result log (OpenCode → Hermes): `.ai/a2a/logs/TASK-<id>.log` (stdout ของ `opencode run`)
- Status: Hermes re-verifies เอง (git diff / รัน test ซ้ำ) — ไม่เชื่อ claim ใน log จนกว่าจะรันเองได้

## Loop
1. Hermes เขียน TASK-<id>.md
2. `bash .ai/a2a/dispatch.sh <task-id>` → รัน opencode run แบบ background, log → logs/
3. Hermes รอจบ → read log → git diff → รัน validation command เอง
4. ผ่าน → mark task done ใน RESULT.md; ไม่ผ่าน → เขียน follow-up brief (loop)

## Rules
- Task ละ 1 workdir เดียว (UGAFStudio repo) — ห้ามรัน parallel sessions ใน repo เดียวกัน
- Brief ต้อง self-contained (engineer ไม่เห็นบทสนทนา)
- Validation command ต้องรันได้ deterministic: `PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest ...`
