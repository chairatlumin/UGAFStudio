*** Settings ***
Documentation     Minimal visual smoke test using UGAF's Robot keywords.
Library           qa_framework.robot.library.UGAFKeywords    output_dir=${OUTPUT DIR}${/}screenshots
Test Setup        Capture Screen

*** Test Cases ***
Game Window Is Rendering
    [Tags]    smoke    fmv    highschoolblood-demo
    Frame Should Not Be Black
    Save Screenshot    game-window

# Input is intentionally opt-in. Add the following setup only after confirming
# the game is the focused window in your current desktop session:
# Test Setup    Enable Game Input
