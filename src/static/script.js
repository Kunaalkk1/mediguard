// ============================================================================
// MediGuard dashboard front-end
// Polls /data for the live environment + AI plan and renders it. The only
// interactive control is the "Simulate Medical Emergency" toggle, which stands
// in for the removed physical SpO2 sensor.
// ============================================================================

// --- Continuous screen scaling (UHD / 4K / mobile proportional sizing) ------
function adjustRootFontSize() {
    const baseWidth = 1440;
    const baseHeight = 900;
    const baseFontSize = 20.5;
    const scale = Math.min(window.innerWidth / baseWidth, window.innerHeight / baseHeight);
    document.documentElement.style.fontSize = (baseFontSize * scale) + 'px';
}
window.addEventListener('resize', adjustRootFontSize);
window.addEventListener('orientationchange', adjustRootFontSize);
adjustRootFontSize();

// --- Real-time clock --------------------------------------------------------
function updateClock() {
    const clockElement = document.getElementById('realtimeClock');
    if (!clockElement) return;
    const now = new Date();
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const day = String(now.getDate()).padStart(2, '0');
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    clockElement.textContent = `${days[now.getDay()]}, ${day}/${month}/${now.getFullYear()} - ${hours}:${minutes}`;
}
setInterval(updateClock, 1000);
updateClock();

// --- Audio ------------------------------------------------------------------
const sirenSound = new Audio('/static/assets/siren.mp3');
sirenSound.loop = true;
let sirenPlaying = false;

function setSiren(on) {
    if (on && !sirenPlaying) {
        sirenSound.currentTime = 0;
        sirenSound.play().then(() => { sirenPlaying = true; })
            .catch(err => console.log('Siren audio blocked:', err));
    } else if (!on && sirenPlaying) {
        sirenSound.pause();
        sirenSound.currentTime = 0;
        sirenPlaying = false;
    }
}

// --- Helpers ----------------------------------------------------------------
function updateSliderBackground(slider) {
    const min = Number(slider.min) || 0;
    const max = Number(slider.max) || 100;
    const percentage = ((Number(slider.value) - min) / (max - min)) * 100;
    slider.style.setProperty('--value', `${percentage}%`);
    slider.style.setProperty('--value-num', percentage);
}

// Closed-world actuator level -> slider percentage (display only).
const LIGHT_PCT = { off: 0, dim: 50, bright: 100 };
const FAN_PCT = { off: 0, low: 25, medium: 50, high: 100 };

// PDDL action -> human-readable step for the plan list.
function humanizeAction(action) {
    const name = (action.match(/\(?\s*([a-z0-9-]+)/i) || [])[1] || action;
    const map = {
        'set-light-off': 'Turn light off',
        'set-light-medium': 'Dim the light',
        'set-light-max': 'Set light to bright',
        'set-fan-off': 'Turn fan off',
        'set-fan-low': 'Set fan to low',
        'set-fan-medium': 'Set fan to medium',
        'set-fan-high': 'Set fan to high',
        'lock-door': 'Lock the door',
        'unlock-door': 'Unlock the door',
        'set-buzzer-off': 'Silence buzzer',
        'set-buzzer-low': 'Buzzer: low alert',
        'set-buzzer-high': 'Buzzer: high alert',
        'set-red-led-off': 'Turn alert LED off',
        'set-red-led-blink': 'Blink alert LED',
    };
    return map[name] || action;
}

// --- Render loop ------------------------------------------------------------
const heartRateEl = document.getElementById('heartRate');
const spo2El = document.getElementById('spo2');
const tempValueEl = document.getElementById('tempValue');
const humidityValueEl = document.getElementById('humidityValue');
const lockBtn = document.getElementById('lockBtn');
const lightSlider = document.getElementById('lightSlider');
const fanSlider = document.getElementById('fanSlider');
const emergencyOverlay = document.getElementById('emergencyOverlay');
const medEmergencyBtn = document.getElementById('medEmergencyBtn');
const sosEmergencyBtn = document.getElementById('sosEmergencyBtn');
const autoBtn = document.getElementById('autoBtn');

// Timestamps of the last user slider drag, so the 1 s /data refresh does not
// yank a slider out from under a finger that is currently adjusting it.
const userAdjust = { light: 0, fan: 0 };
let manualMode = false;
let doorLocked = true;      // last known door state (for the lock toggle)
let lockEnabled = true;     // false during an emergency (door forced unlocked)

function renderVitals(data) {
    if (heartRateEl) heartRateEl.textContent = data.heart_rate != null ? data.heart_rate : '--';
    if (spo2El) spo2El.textContent = data.spo2 != null ? data.spo2 : '--';
    if (tempValueEl && data.temperature != null) tempValueEl.textContent = `${Math.round(data.temperature)}°C`;
    if (humidityValueEl && data.humidity != null) humidityValueEl.textContent = `${Math.round(data.humidity)}%`;
}

// Env-controls card: door icon + light/fan sliders. In AUTO the sliders mirror
// the planner-driven state (disabled); in MANUAL they are the live control.
function renderControls(data) {
    const act = data.actuator_state || {};
    const mode = data.mode || { manual: false, light: 0, fan: 0 };
    const emergencyActive = !!(data.emergency && data.emergency.active);
    manualMode = !!mode.manual;

    // Sliders are live only in manual mode with no emergency (safety wins).
    const controllable = manualMode && !emergencyActive;
    if (autoBtn) autoBtn.classList.toggle('active', !manualMode);  // glow = AUTO
    if (lightSlider) lightSlider.disabled = !controllable;
    if (fanSlider) fanSlider.disabled = !controllable;

    // Door: manual lock/unlock is available any time except during an
    // emergency, when it is forced unlocked and the toggle is disabled.
    doorLocked = act.door !== 'unlocked';
    lockEnabled = !emergencyActive;
    if (lockBtn) {
        lockBtn.src = doorLocked
            ? '/static/assets/Locked_Button.png'
            : '/static/assets/Unlocked_Button.png';
        lockBtn.style.opacity = lockEnabled ? '1' : '0.5';
        lockBtn.style.cursor = lockEnabled ? 'pointer' : 'not-allowed';
    }

    const now = Date.now();
    if (lightSlider && now - userAdjust.light > 1200) {
        const v = manualMode ? mode.light : (LIGHT_PCT[act.light] != null ? LIGHT_PCT[act.light] : 0);
        lightSlider.value = v;
        updateSliderBackground(lightSlider);
    }
    if (fanSlider && now - userAdjust.fan > 1200) {
        const v = manualMode ? mode.fan : (FAN_PCT[act.fan] != null ? FAN_PCT[act.fan] : 0);
        fanSlider.value = v;
        updateSliderBackground(fanSlider);
    }
}

// --- Closed-world boolean PDDL facts ---------------------------------------
// Multi-valued room + patient state as their one-hot PDDL predicates.
function stateFacts(data) {
    const room = String(data.room_state || '').toLowerCase();
    let patient = String(data.patient_state || '').toLowerCase();
    if (patient === 'out of bed') patient = 'out-of-bed';
    else if (patient === 'distressed') patient = 'distress';
    return [
        ['room-normal', room === 'normal'],
        ['room-hazardous', room === 'hazardous'],
        ['room-emergency', room === 'emergency'],
        ['patient-awake', patient === 'awake'],
        ['patient-resting', patient === 'resting'],
        ['patient-out-of-bed', patient === 'out-of-bed'],
        ['patient-distress', patient === 'distress'],
    ];
}

// Actuator closed states, encoded exactly as the domain's boolean predicates.
function actuatorFacts(act) {
    const light = act.light || 'off';
    const fan = act.fan || 'off';
    const door = act.door || 'locked';
    const buzzer = act.buzzer || 'off';
    const led = act.red_led || 'off';
    return [
        ['light-on', light !== 'off'],
        ['light-dim', light === 'dim'],
        ['fan-on', fan !== 'off'],
        ['fan-medium', fan === 'medium'],
        ['fan-high', fan === 'high'],
        ['door-locked', door === 'locked'],
        ['door-unlocked', door === 'unlocked'],
        ['buzzer-on', buzzer !== 'off'],
        ['buzzer-high', buzzer === 'high'],
        ['red-led-on', led !== 'off'],
        ['red-led-blinking', led === 'blink'],
    ];
}

// Observed sensor facts, matching observation_predicates() in the planner.
function observationFacts(summary, outOfBedMinutes) {
    const s = summary || {};
    return [
        ['sos-pressed', !!s.sos_pressed],
        ['air-hazardous', s.air_quality_status === 'unsafe'],
        ['temperature-unsafe', s.temperature_status === 'unsafe'],
        ['temperature-hot', s.temperature_status === 'hot'],
        ['humidity-high', s.humidity_status === 'high'],
        ['room-dark', s.light_level === 'dark'],
        ['patient-on-bed', !!s.pressure_on_bed],
        ['motion-recent', !!s.pir_motion_last_15_min],
        ['spo2-low', s.spo2_status === 'low'],
        ['pulse-abnormal', s.pulse_status === 'abnormal'],
        ['out-of-bed-alert-due', Number(outOfBedMinutes || 0) >= 15],
    ];
}

const pddlFactsEl = document.getElementById('pddlFacts');

function renderFacts(data) {
    if (!pddlFactsEl) return;
    const facts = stateFacts(data)
        .concat(observationFacts(data.sensor_summary, data.out_of_bed_minutes))
        .concat(actuatorFacts(data.actuator_state || {}));
    pddlFactsEl.innerHTML = facts.map(([name, value]) =>
        `<div class="fact"><span class="fact-name">${name}</span>` +
        `<span class="fact-val ${value ? 'is-true' : 'is-false'}">${value ? 'TRUE' : 'FALSE'}</span></div>`
    ).join('');
}

function renderEmergency(data) {
    const emergency = data.emergency || { active: false };
    const active = !!emergency.active;
    if (emergencyOverlay) emergencyOverlay.classList.toggle('active', active);
    document.body.classList.toggle('emergency-active', active);
    setSiren(active);
}

function renderMedButton(toggles) {
    if (medEmergencyBtn) {
        const on = !!(toggles && toggles.vitals_emergency);
        medEmergencyBtn.classList.toggle('active', on);
        medEmergencyBtn.textContent = on ? 'Clear Medical Emergency' : 'Simulate Medical Emergency';
    }
    if (sosEmergencyBtn) {
        const on = !!(toggles && toggles.sos_emergency);
        sosEmergencyBtn.classList.toggle('active', on);
        sosEmergencyBtn.textContent = on ? 'Clear SOS Emergency' : 'Trigger SOS Emergency';
    }
}

const planGoal = document.getElementById('planGoal');
const planPriority = document.getElementById('planPriority');
const planStatus = document.getElementById('planStatus');
const planActions = document.getElementById('planActions');
const planName = document.getElementById('planName');
const planTime = document.getElementById('planTime');

function renderPlan(plan) {
    if (!plan || !planGoal) return;
    planGoal.textContent = plan.goal || '—';

    const priority = (plan.priority || 'normal').toLowerCase();
    if (planPriority) {
        planPriority.textContent = priority.toUpperCase();
        planPriority.setAttribute('data-priority', priority);
    }

    if (planStatus) {
        const failed = plan.status && plan.status !== 'plan_found';
        planStatus.textContent = failed ? (plan.status || '').replace(/_/g, ' ') : '';
        planStatus.classList.toggle('failed', !!failed);
    }

    if (planActions) {
        const actions = Array.isArray(plan.plan) ? plan.plan : [];
        planActions.innerHTML = '';
        if (actions.length === 0) {
            const li = document.createElement('li');
            li.className = 'plan-empty';
            li.textContent = plan.status === 'planner_failed'
                ? 'Planner unavailable — running on local safety profile.'
                : 'No actions required.';
            planActions.appendChild(li);
        } else {
            actions.forEach(action => {
                const li = document.createElement('li');
                li.textContent = humanizeAction(action);
                planActions.appendChild(li);
            });
        }
    }

    if (planName) {
        planName.textContent = plan.planner_name
            ? `${plan.planner_name} (${plan.planner_mode || 'online'})`
            : 'PDDL planner';
    }
    if (planTime && plan.timestamp) {
        planTime.textContent = plan.timestamp.replace('T', ' ');
    }
}

async function refresh() {
    try {
        const res = await fetch('/data', { cache: 'no-store' });
        if (!res.ok) return;
        const data = await res.json();
        renderVitals(data);
        renderControls(data);
        renderFacts(data);
        renderEmergency(data);
        renderMedButton(data.toggles);
        renderPlan(data.plan);
    } catch (err) {
        console.log('refresh failed:', err);
    }
}
setInterval(refresh, 1000);
refresh();

// --- Door lock/unlock (press and hold 0.5 s) --------------------------------
const lockProgressFill = document.getElementById('lockProgressFill');
const LOCK_HOLD_MS = 500;
const LOCK_MAX_OFFSET = 234.3;
let lockRaf = null;
let lockStart = 0;

function lockProgressStep() {
    const progress = Math.min((Date.now() - lockStart) / LOCK_HOLD_MS, 1);
    if (lockProgressFill) lockProgressFill.style.strokeDashoffset = LOCK_MAX_OFFSET * (1 - progress);
    if (progress >= 1) {
        toggleDoor();
        resetLockProgress();
    } else {
        lockRaf = requestAnimationFrame(lockProgressStep);
    }
}

function startLockHold(e) {
    if (!lockEnabled) return;                 // disabled during an emergency
    if (e.type === 'touchstart') e.preventDefault();
    if (lockBtn) lockBtn.style.transform = 'scale(0.95)';
    lockStart = Date.now();
    lockProgressStep();
}

function resetLockProgress() {
    if (lockRaf) { cancelAnimationFrame(lockRaf); lockRaf = null; }
    if (lockBtn) lockBtn.style.transform = 'scale(1)';
    if (lockProgressFill) lockProgressFill.style.strokeDashoffset = LOCK_MAX_OFFSET;
}

function toggleDoor() {
    const value = doorLocked ? 'unlocked' : 'locked';
    doorLocked = !doorLocked;                 // optimistic; /data confirms
    if (lockBtn) {
        lockBtn.src = doorLocked
            ? '/static/assets/Locked_Button.png'
            : '/static/assets/Unlocked_Button.png';
    }
    fetch('/api/manual/door', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
    }).then(() => refresh()).catch(err => console.log('door toggle failed:', err));
}

if (lockBtn) {
    lockBtn.style.transition = 'transform 0.2s';
    lockBtn.addEventListener('mousedown', startLockHold);
    lockBtn.addEventListener('mouseup', resetLockProgress);
    lockBtn.addEventListener('mouseleave', resetLockProgress);
    lockBtn.addEventListener('touchstart', startLockHold, { passive: false });
    lockBtn.addEventListener('touchend', resetLockProgress);
    lockBtn.addEventListener('touchcancel', resetLockProgress);
}

// --- Manual / auto control interactions -------------------------------------
const lastPost = { light: 0, fan: 0 };

function postManual(kind, value, force) {
    // Throttle mid-drag traffic; `force` (on release) always sends the final value.
    const now = Date.now();
    if (!force && now - lastPost[kind] < 120) return;
    lastPost[kind] = now;
    fetch(`/api/manual/${kind}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: Number(value) }),
    }).catch(err => console.log('manual', kind, 'failed:', err));
}

function wireSlider(slider, kind) {
    if (!slider) return;
    slider.addEventListener('input', e => {
        userAdjust[kind] = Date.now();
        updateSliderBackground(e.target);
        if (manualMode) postManual(kind, e.target.value, false);
    });
    slider.addEventListener('change', e => {
        userAdjust[kind] = Date.now();
        if (manualMode) postManual(kind, e.target.value, true);
    });
}
wireSlider(lightSlider, 'light');
wireSlider(fanSlider, 'fan');

if (autoBtn) {
    autoBtn.addEventListener('click', async () => {
        try {
            const res = await fetch('/api/mode/toggle', { method: 'POST' });
            const body = await res.json();
            manualMode = !!body.manual_mode;
        } catch (err) {
            console.log('mode toggle failed:', err);
        } finally {
            refresh();
        }
    });
}

// --- Emergency simulation toggles -------------------------------------------
function wireEmergencyButton(btn, endpoint) {
    if (!btn) return;
    btn.addEventListener('click', async () => {
        btn.disabled = true;
        try {
            await fetch(endpoint, { method: 'POST' });
        } catch (err) {
            console.log('emergency toggle failed:', err);
        } finally {
            btn.disabled = false;
            refresh();
        }
    });
}
wireEmergencyButton(medEmergencyBtn, '/api/emergency/vitals/toggle');
wireEmergencyButton(sosEmergencyBtn, '/api/emergency/sos/toggle');

// --- Auto full-screen -------------------------------------------------------
// Browsers only allow fullscreen from a user gesture, so we try immediately
// (works in kiosk/allowed contexts) and otherwise trigger on the first tap,
// click or key press. Once fullscreen is active the handlers are no-ops.
function goFullscreen() {
    const el = document.documentElement;
    const request = el.requestFullscreen || el.webkitRequestFullscreen || el.msRequestFullscreen;
    if (!request || document.fullscreenElement || document.webkitFullscreenElement) return;
    try {
        const result = request.call(el);
        if (result && typeof result.catch === 'function') result.catch(() => {});
    } catch (err) {
        /* blocked without a gesture -- the interaction handlers will retry */
    }
}

window.addEventListener('load', goFullscreen);
['pointerdown', 'touchend', 'keydown'].forEach(evt =>
    document.addEventListener(evt, goFullscreen, { passive: true }));

// --- Service worker (PWA) ---------------------------------------------------
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
            .then(reg => console.log('MediGuard Service Worker registered:', reg.scope))
            .catch(err => console.error('MediGuard Service Worker registration failed:', err));
    });
}
