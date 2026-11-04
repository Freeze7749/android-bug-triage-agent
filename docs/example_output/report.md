# SIM card absent or in error state

**Draft, needs human review.** Analyzer: `rules`. Top category: `sim_failure`. Severity: Critical. Component: Telephony/SIM.

Source: `samples/demo_sim_failure.log` (154 lines, 19 templates)

## Summary
Keyword rules matched: sim_failure, network_registration_lost.

## Steps to reproduce
1. Not known from the log: add the steps used during the test.

## Actual result
10-15 10:27:04.534  1146  1149 D UiccController: handleSimStatus: cardState=ABSENT slot=0

## Expected result
The SIM is detected and ready.

## Possible causes

### 1. `sim_failure` (low confidence)
2 line(s) match the rule for sim_failure.

- [demo_sim_failure.log:61](samples/demo_sim_failure.log#L61): `10-15 10:27:04.534  1146  1149 D UiccController: handleSimStatus: cardState=ABSENT slot=0`
- [demo_sim_failure.log:63](samples/demo_sim_failure.log#L63): `10-15 10:27:04.740  1146  1157 D RILJ    : [1935]< GET_SIM_STATUS IccCardState {CARDSTATE_ABSENT,PINSTATE_UNKNOWN} [PHONE0]`

### 2. `network_registration_lost` (low confidence)
1 line(s) match the rule for network_registration_lost.

- [demo_sim_failure.log:64](samples/demo_sim_failure.log#L64): `10-15 10:27:04.969  1146  1154 D ServiceStateTracker: Poll ServiceState done: mVoiceRegState=1(OUT_OF_SERVICE) mDataRegState=1(OUT_OF_SERVICE) rat=UNKNOWN`
