*** Settings ***
Documentation     Local-only Decision API preflight; model actions are restricted to noop.
Library           qa_framework.robot.library.UGAFKeywords    output_dir=${OUTPUT DIR}${/}screenshots
Test Setup        Capture Screen

*** Variables ***
${EXPECTED_MODEL}    qwen/qwen2.5-vl-7b

*** Test Cases ***
Decision API And VLM Are Ready
    [Tags]    preflight    decision-api
    ${health}=    Decision API Should Be Ready    ${EXPECTED_MODEL}
    Should Be Equal    ${health}[status]    ready

VLM Can Inspect A Frame Without Game Input
    [Tags]    preflight    decision-api    vision
    ${decision}=    Ask Next Action    Inspect this frame for QA readiness only. Do not choose a route.    allowed_actions=noop
    Should Be Equal    ${decision}[action]    noop
    Should Be Equal    ${decision}[fallback]    ${False}
