"""Generate the labelled evaluation logs. All content is synthetic and written for this project.

Each fault class has several scenario variants, modelled on public AOSP log formats. The dev split
uses the first two variants of each class. The test split uses only the remaining variants, so the
rules and the prompt are never tuned on the scenarios they are scored on.

A fault line is marked key=True. Its line number goes into labels.json as `key_lines`.
"""
import json
import random
import shutil
from pathlib import Path

SEED = 20261104
DEV_PER_CLASS = 3
TEST_PER_CLASS = 5
DATASET = Path(__file__).parent / "dataset"
APPS = ["com.example.notes", "com.example.camera", "com.example.maps", "com.example.chat", "com.example.music"]


def _app(r):
    return r.choice(APPS)


def _line(tag, level, message, key=False):
    return {"tag": tag, "level": level, "message": message, "key": key}


# ---- Background chatter, present in every log ----
def _noise(r):
    return r.choice(
        [
            lambda: _line("RILJ", "D", f"[UNSL]< UNSOL_SIGNAL_STRENGTH {{ssRsrp={r.randint(-110, -80)}, ssSinr={r.randint(2, 25)}}} [PHONE0]"),
            lambda: _line("RILJ", "D", f"[{r.randint(1000, 9999)}]> GET_CURRENT_CALLS [PHONE0]"),
            lambda: _line("RILJ", "D", f"[{r.randint(1000, 9999)}]< OPERATOR {{Example Net, ExNet, 23001}} [PHONE0]"),
            lambda: _line("ServiceStateTracker", "D", "Poll ServiceState done: mVoiceRegState=0(IN_SERVICE) mDataRegState=0(IN_SERVICE) rat=NR"),
            lambda: _line("ActivityManager", "I", f"Start proc {r.randint(1000, 30000)}:{_app(r)}/u0a{r.randint(100, 300)} for activity"),
            lambda: _line("ActivityTaskManager", "I", f"Displayed {_app(r)}/.MainActivity: +{r.randint(200, 900)}ms"),
            lambda: _line("WifiService", "D", f"getWifiEnabledState uid={r.randint(1000, 12000)}"),
            lambda: _line("BatteryService", "I", f"Processing new values: level={r.randint(20, 99)} temperature={r.randint(250, 390)}"),
            lambda: _line("chatty", "I", f"uid={r.randint(1000, 12000)} identical {r.randint(2, 30)} lines"),
            lambda: _line("OpenGLRenderer", "I", f"Davey! duration={r.randint(700, 1400)}ms"),
            lambda: _line("chromium", "E", f"[ERROR:cache_util.cc({r.randint(50, 200)})] Unable to move cache folder"),
            lambda: _line("libEGL", "W", "EGLNativeWindowType has invalid format"),
            lambda: _line("DnsResolver", "D", f"res_nquery: netid={r.randint(100, 120)} rcode=0"),
            lambda: _line("Bluetooth", "W", "Scan not started: adapter is off"),
            lambda: _line("AudioFlinger", "D", f"mixer(0x{r.randint(4096, 65535):x}) throttle end"),
        ]
    )()


# ---- Java crash ----
def java_npe(r):
    app = _app(r)
    return [
        _line("AndroidRuntime", "E", "FATAL EXCEPTION: main", True),
        _line("AndroidRuntime", "E", f"Process: {app}, PID: {r.randint(1000, 30000)}", True),
        _line("AndroidRuntime", "E", "java.lang.NullPointerException: Attempt to invoke virtual method 'int java.lang.String.length()' on a null object reference", True),
        _line("AndroidRuntime", "E", f"\tat {app}.ui.EditorFragment.onResume(EditorFragment.java:{r.randint(20, 400)})"),
        _line("ActivityManager", "W", f"Force finishing activity {app}/.MainActivity"),
    ]


def java_state(r):
    app = _app(r)
    return [
        _line("AndroidRuntime", "E", "FATAL EXCEPTION: main", True),
        _line("AndroidRuntime", "E", f"Process: {app}, PID: {r.randint(1000, 30000)}", True),
        _line("AndroidRuntime", "E", "java.lang.IllegalStateException: Fragment not attached to a context.", True),
        _line("ActivityManager", "I", f"Process {app} (pid {r.randint(1000, 30000)}) has died"),
    ]


def java_background(r):
    app = _app(r)
    return [
        _line("AndroidRuntime", "E", f"FATAL EXCEPTION: pool-{r.randint(1, 5)}-thread-{r.randint(1, 8)}", True),
        _line("AndroidRuntime", "E", f"Process: {app}, PID: {r.randint(1000, 30000)}", True),
        _line("AndroidRuntime", "E", "java.lang.ArrayIndexOutOfBoundsException: length=4; index=4", True),
    ]


def java_finish_only(r):
    app = _app(r)
    return [
        _line("DEBUG_APP", "E", f"Uncaught exception in thread main of {app}: java.lang.ClassCastException", True),
        _line("ActivityManager", "W", f"crash in {app}: Force finishing activity {app}/.MainActivity", True),
        _line("ActivityManager", "I", f"Process {app} (pid {r.randint(1000, 30000)}) has died: fg TOP"),
    ]


# ---- ANR ----
def anr_input(r):
    app = _app(r)
    return [
        _line("ActivityManager", "E", f"ANR in {app} ({app}/.MainActivity)", True),
        _line("ActivityManager", "E", "Reason: Input dispatching timed out (Waiting to send non-key event)", True),
        _line("ActivityManager", "E", f"Load: {r.uniform(1, 9):.2f} / {r.uniform(1, 9):.2f} / {r.uniform(1, 9):.2f}"),
    ]


def anr_broadcast(r):
    app = _app(r)
    return [
        _line("ActivityManager", "E", f"ANR in {app}", True),
        _line("ActivityManager", "E", f"Reason: Broadcast of Intent {{ act=android.intent.action.SCREEN_ON cmp={app}/.Receiver }}", True),
    ]


def anr_service(r):
    app = _app(r)
    return [
        _line("ActivityManager", "W", f"Timeout executing service: ServiceRecord{{{r.randint(4096, 65535):x} u0 {app}/.SyncService}}", True),
        _line("ActivityManager", "E", f"ANR in {app}", True),
    ]


def anr_dispatcher(r):
    app = _app(r)
    return [
        _line("InputDispatcher", "W", f"Application is not responding: {app}/.MainActivity. It has been {r.uniform(5000, 9000):.1f}ms since event", True),
        _line("WindowManager", "W", f"Input event dispatching timed out sending to {app}/.MainActivity", True),
    ]


# ---- Native crash ----
def native_segv(r):
    app = _app(r)
    pid = r.randint(1000, 30000)
    return [
        _line("libc", "F", f"Fatal signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0 in tid {pid} (RenderThread), pid {pid} ({app})", True),
        _line("DEBUG", "F", "*** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***"),
        _line("DEBUG", "F", f"pid: {pid}, tid: {pid}, name: RenderThread  >>> {app} <<<", True),
    ]


def native_abort(r):
    app = _app(r)
    pid = r.randint(1000, 30000)
    return [
        _line("libc", "F", f"Fatal signal 6 (SIGABRT), code -1 (SI_QUEUE) in tid {pid} (main), pid {pid} ({app})", True),
        _line("DEBUG", "F", "Abort message: 'FORTIFY: pthread_mutex_lock called on a destroyed mutex'", True),
    ]


def native_tombstone_only(r):
    app = _app(r)
    pid = r.randint(1000, 30000)
    return [
        _line("DEBUG", "F", f"pid: {pid}, tid: {pid}, name: worker  >>> {app} <<<", True),
        _line("DEBUG", "F", "signal 7 (SIGBUS), code 2 (BUS_ADRERR), fault addr 0x7a10", True),
        _line("tombstoned", "I", f"received crash request for pid {pid}"),
    ]


def native_check(r):
    app = _app(r)
    pid = r.randint(1000, 30000)
    return [
        _line("DEBUG", "F", f"Cmdline: {app}", True),
        _line("DEBUG", "F", "signal 4 (SIGILL), code 1 (ILL_ILLOPC), fault addr 0x70cc", True),
        _line("ActivityManager", "I", f"Process {app} (pid {pid}) has died: vis VIS"),
    ]


# ---- Out of memory ----
def oom_java(r):
    app = _app(r)
    return [
        _line("AndroidRuntime", "E", "FATAL EXCEPTION: main"),
        _line("AndroidRuntime", "E", f"Process: {app}, PID: {r.randint(1000, 30000)}"),
        _line("AndroidRuntime", "E", f"java.lang.OutOfMemoryError: Failed to allocate a {r.randint(10, 90) * 1000000} byte allocation with 4194304 free bytes", True),
    ]


def oom_lmk(r):
    app = _app(r)
    return [
        _line("lowmemorykiller", "I", f"Kill '{app}' ({r.randint(1000, 30000)}), uid 10123, oom_score_adj 0 to free {r.randint(50000, 300000)}kB", True),
        _line("ActivityManager", "I", f"Process {app} (pid {r.randint(1000, 30000)}) has died: fg TOP", True),
    ]


def oom_lmkd(r):
    app = _app(r)
    return [
        _line("lmkd", "I", f"Reclaimed {r.randint(50000, 300000)}kB by killing {app}, oom_score_adj 0, memory pressure critical", True),
        _line("ActivityManager", "I", f"Low on memory: foreground process {app} removed", True),
    ]


def oom_kernel(r):
    app = _app(r)
    return [
        _line("kernel", "E", f"Out of memory: Killed process {r.randint(1000, 30000)} ({app}) total-vm:{r.randint(4000000, 9000000)}kB", True),
        _line("kernel", "I", "oom_reaper: reaped process", True),
    ]


# ---- Consequences that follow a telephony root cause ----
def _lost_data():
    return _line("DataNetworkController", "D", "Data network disconnected: reason=NOT_IN_SERVICE")


def _lost_ims():
    return _line("ImsPhone", "D", "IMS deregistered: no data connection")


# ---- Registration lost ----
def reg_oos(r):
    return [
        _line("ServiceStateTracker", "D", "Poll ServiceState done: mVoiceRegState=1(OUT_OF_SERVICE) mDataRegState=1(OUT_OF_SERVICE) rat=UNKNOWN", True),
        _line("ServiceStateTracker", "D", "Poll ServiceState done: mVoiceRegState=1(OUT_OF_SERVICE) mDataRegState=1(OUT_OF_SERVICE) rat=UNKNOWN", True),
        _lost_data(),
        _lost_ims(),
    ]


def reg_reject(r):
    cause = r.choice([3, 7, 11, 15])
    return [
        _line("RILJ", "D", f"[{r.randint(1000, 9999)}]< DATA_REGISTRATION_STATE {{regState=NOT_REG_NOT_SEARCHING, rejectCause={cause}}} [PHONE0]", True),
        _line("ServiceStateTracker", "E", f"Registration denied by network, rejectCause={cause}", True),
        _lost_data(),
    ]


def reg_at_denied(r):
    return [
        _line("AT", "D", "AT< +C5GREG: 3", True),
        _line("AT", "D", "AT< +CEREG: 3", True),
        _line("NetworkMonitor", "W", "Cellular network not available: registration denied", True),
        _lost_data(),
    ]


def reg_rlf(r):
    return [
        _line("MDMCTRL", "W", f"Radio link failure on cell pci={r.randint(1, 500)}, re-establishment rejected", True),
        _line("ServiceState", "D", "serviceState changed: voice=NOT_REG data=NOT_REG emergencyOnly=true", True),
        _lost_ims(),
    ]


# ---- Data call failure ----
def data_apn(r):
    return [
        _line("RILJ", "D", f"[{r.randint(1000, 9999)}]> SETUP_DATA_CALL apn=internet [PHONE0]"),
        _line("DataNetwork", "E", "onSetupResponse: resultCode=1 cause=MISSING_UNKNOWN_APN", True),
        _line("DataNetwork", "E", "onSetupResponse: resultCode=1 cause=MISSING_UNKNOWN_APN", True),
    ]


def data_ril(r):
    return [
        _line("RILJ", "E", f"[{r.randint(1000, 9999)}]< SETUP_DATA_CALL error: com.android.internal.telephony.CommandException: RADIO_NOT_AVAILABLE", True),
        _line("DataServiceManager", "D", "setupDataCall completed with failure, retry in 5000ms"),
        _line("RILJ", "E", f"[{r.randint(1000, 9999)}]< SETUP_DATA_CALL error: com.android.internal.telephony.CommandException: RADIO_NOT_AVAILABLE", True),
    ]


def data_dct(r):
    cause = r.choice(["INSUFFICIENT_RESOURCES", "USER_AUTHENTICATION", "SERVICE_OPTION_NOT_SUBSCRIBED"])
    return [
        _line("DCT", "D", f"onDataSetupComplete: error apn=internet cause={cause}", True),
        _line("DCT", "D", f"onDataSetupComplete: error apn=internet cause={cause}", True),
        _line("ConnectivityService", "D", "NetworkAgentInfo [MOBILE] not validated, no default network"),
    ]


def data_pdn(r):
    return [
        _line("AT", "D", "AT< +CGEV: ME PDN ACT REJECT cid=1 cause=33", True),
        _line("QNS", "W", "PDN activation rejected by network for apn=internet", True),
    ]


# ---- IMS ----
def ims_forbidden(r):
    return [
        _line("ImsRegistrationTracker", "E", "REGISTER failed: SIP/2.0 403 Forbidden", True),
        _line("ImsPhone", "D", "VoLTE unavailable after registration failure"),
    ]


def ims_disconnected(r):
    return [
        _line("ImsPhoneCallTracker", "D", "onImsDisconnected: imsReasonInfo code=1000 extra=0", True),
        _line("ImsManager", "W", "IMS not registered, VoLTE calls will use circuit switched fallback"),
    ]


def ims_timeout(r):
    return [
        _line("ImsService", "W", f"REGISTER timed out after {r.randint(30, 64)}s, no response from P-CSCF", True),
        _line("ImsService", "W", "IMS registration attempt exhausted, backing off", True),
    ]


def ims_auth(r):
    return [
        _line("VoLteStack", "E", "AKA authentication failed: MAC mismatch on IMS REGISTER challenge", True),
        _line("ImsPhone", "D", "isVolteEnabled=false after failed registration", True),
    ]


# ---- SIM ----
def sim_absent(r):
    return [
        _line("UiccController", "D", "handleSimStatus: cardState=ABSENT slot=0", True),
        _line("RILJ", "D", f"[{r.randint(1000, 9999)}]< GET_SIM_STATUS IccCardState {{CARDSTATE_ABSENT,PINSTATE_UNKNOWN}} [PHONE0]", True),
        _line("ServiceStateTracker", "D", "Poll ServiceState done: mVoiceRegState=1(OUT_OF_SERVICE) mDataRegState=1(OUT_OF_SERVICE) rat=UNKNOWN"),
        _lost_data(),
        _lost_ims(),
    ]


def sim_error(r):
    return [
        _line("RILJ", "D", f"[{r.randint(1000, 9999)}]< GET_SIM_STATUS IccCardState {{CARDSTATE_ERROR,PINSTATE_UNKNOWN}} [PHONE0]", True),
        _line("UiccCard", "E", "Card state changed to CARDSTATE_ERROR", True),
        _line("ServiceStateTracker", "D", "Poll ServiceState done: mVoiceRegState=1(OUT_OF_SERVICE) mDataRegState=1(OUT_OF_SERVICE) rat=UNKNOWN"),
    ]


def sim_restricted(r):
    return [
        _line("UiccProfile", "E", "CARDSTATE_RESTRICTED: carrier restriction rules not met for slot 0", True),
        _line("SubscriptionManager", "W", "No active subscription: card restricted", True),
        _lost_data(),
    ]


def sim_io(r):
    return [
        _line("IccFileHandler", "E", f"SIM I/O failed: sw1=0x6f sw2=0x{r.randint(0, 255):02x} reading EF_IMSI", True),
        _line("SubscriptionManager", "W", "SIM records not loaded, no active subscription", True),
        _line("DataNetworkController", "D", "Data network disconnected: reason=NOT_IN_SERVICE"),
    ]


# ---- No fault: includes errors that look alarming but recover ----
def clean(r):
    return []


def flap_recovers(r):
    return [
        _line("ServiceStateTracker", "D", "Poll ServiceState done: mVoiceRegState=1(OUT_OF_SERVICE) mDataRegState=1(OUT_OF_SERVICE) rat=UNKNOWN"),
        _line("ServiceStateTracker", "D", "Poll ServiceState done: mVoiceRegState=0(IN_SERVICE) mDataRegState=0(IN_SERVICE) rat=NR"),
        _line("DataNetwork", "D", "onSetupResponse: resultCode=0 cause=NONE"),
    ]


def handled_and_retry(r):
    return [
        _line("System.err", "W", "java.io.IOException: unexpected end of stream"),
        _line("SyncAdapter", "I", "Sync failed, handled, will retry"),
        _line("RILJ", "E", f"[{r.randint(1000, 9999)}]< SETUP_DATA_CALL error: com.android.internal.telephony.CommandException: OP_NOT_ALLOWED_DURING_VOICE_CALL"),
        _line("DataNetwork", "D", "onSetupResponse: resultCode=0 cause=NONE"),
    ]


def airplane_mode(r):
    return [
        _line("ConnectivityService", "I", "Airplane mode enabled by user"),
        _line("RILJ", "D", f"[{r.randint(1000, 9999)}]> RADIO_POWER on=false [PHONE0]"),
        _line("ServiceStateTracker", "D", "Poll ServiceState done: mVoiceRegState=3(POWER_OFF) mDataRegState=1(OUT_OF_SERVICE) rat=UNKNOWN"),
        _line("ImsPhoneCallTracker", "D", "onImsDisconnected: imsReasonInfo code=1016 extra=airplane mode"),
        _line("ConnectivityService", "I", "Airplane mode disabled by user"),
        _line("ServiceStateTracker", "D", "Poll ServiceState done: mVoiceRegState=0(IN_SERVICE) mDataRegState=0(IN_SERVICE) rat=NR"),
    ]


SCENARIOS = {
    "java_crash": [java_npe, java_state, java_background, java_finish_only],
    "anr": [anr_input, anr_broadcast, anr_service, anr_dispatcher],
    "native_crash": [native_segv, native_abort, native_tombstone_only, native_check],
    "out_of_memory": [oom_java, oom_lmk, oom_lmkd, oom_kernel],
    "network_registration_lost": [reg_oos, reg_reject, reg_at_denied, reg_rlf],
    "data_call_failure": [data_apn, data_ril, data_dct, data_pdn],
    "ims_registration_failure": [ims_forbidden, ims_disconnected, ims_timeout, ims_auth],
    "sim_failure": [sim_absent, sim_error, sim_restricted, sim_io],
    "no_fault": [clean, flap_recovers, handled_and_retry, airplane_mode],
}


def build_case(scenario, r: random.Random) -> tuple[list[str], list[int]]:
    """Mix the scenario's lines into background noise. Return (log lines, key line numbers)."""
    entries = [_noise(r) for _ in range(r.randint(40, 90))]
    for item in scenario(r):
        entries.append(item)
        entries.extend(_noise(r) for _ in range(r.randint(0, 3)))
    entries.extend(_noise(r) for _ in range(r.randint(40, 90)))

    pid, milliseconds = r.randint(800, 3000), r.randint(0, 3_000_000)
    lines, key_lines = [], []
    for number, entry in enumerate(entries, start=1):
        milliseconds += r.randint(1, 400)
        seconds, ms = divmod(milliseconds, 1000)
        minutes, sec = divmod(seconds, 60)
        hours, minute = divmod(minutes, 60)
        stamp = f"10-15 {10 + hours:02d}:{minute:02d}:{sec:02d}.{ms:03d}"
        lines.append(f"{stamp} {pid:5d} {pid + r.randint(0, 40):5d} {entry['level']} {entry['tag']:<8s}: {entry['message']}")
        if entry["key"]:
            key_lines.append(number)
    return lines, key_lines


def main() -> None:
    r = random.Random(SEED)
    if DATASET.exists():
        shutil.rmtree(DATASET)
    for split, per_class, slice_start, slice_end in [("dev", DEV_PER_CLASS, 0, 2), ("test", TEST_PER_CLASS, 2, None)]:
        folder = DATASET / split
        folder.mkdir(parents=True)
        labels = []
        for category, variants in SCENARIOS.items():
            pool = variants[slice_start:slice_end]
            for index in range(per_class):
                scenario = pool[index % len(pool)]
                lines, key_lines = build_case(scenario, r)
                name = f"{category}_{index + 1:02d}.log"
                (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
                labels.append({"file": name, "category": category, "scenario": scenario.__name__, "key_lines": key_lines})
        (folder / "labels.json").write_text(json.dumps(labels, indent=1), encoding="utf-8", newline="\n")
        print(f"{split}: {len(labels)} cases")


if __name__ == "__main__":
    main()
