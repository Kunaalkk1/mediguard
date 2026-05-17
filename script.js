// Real-time Clock Update
function updateClock() {
    const clockElement = document.getElementById('realtimeClock');
    const now = new Date();
    
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const dayName = days[now.getDay()];
    
    const day = String(now.getDate()).padStart(2, '0');
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const year = now.getFullYear();
    
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    
    clockElement.textContent = `${dayName}, ${day}/${month}/${year} - ${hours}:${minutes}`;
}

setInterval(updateClock, 1000);
updateClock(); // Initial call

// Door Lock Toggle (Single Image)
const lockBtn = document.getElementById('lockBtn');
const lockProgressFill = document.getElementById('lockProgressFill');
let isLocked = true;
let lockAnimationFrameId;
let lockStartTime;
const lockHoldDuration = 1000; // 1 second
const lockMaxOffset = 234.3;

function toggleLock() {
    isLocked = !isLocked;
    if (isLocked) {
        lockBtn.src = 'assets/Locked_Button.png';
    } else {
        lockBtn.src = 'assets/Unlocked_Button.png';
    }
}

function updateLockProgress() {
    const elapsed = Date.now() - lockStartTime;
    let progress = Math.min(elapsed / lockHoldDuration, 1);
    
    const currentOffset = lockMaxOffset - (progress * lockMaxOffset);
    if (lockProgressFill) lockProgressFill.style.strokeDashoffset = currentOffset;
    
    if (progress >= 1) {
        toggleLock();
        resetLockProgress();
    } else {
        lockAnimationFrameId = requestAnimationFrame(updateLockProgress);
    }
}

function startLockHold(e) {
    if (emergencyOverlay && emergencyOverlay.classList.contains('active')) return;
    if (e.type === 'touchstart') e.preventDefault();
    lockBtn.style.transform = 'scale(0.95)';
    lockBtn.style.opacity = '0.8';
    
    lockStartTime = Date.now();
    updateLockProgress();
}

function cancelLockHold() {
    cancelAnimationFrame(lockAnimationFrameId);
    resetLockProgress();
}

function resetLockProgress() {
    lockBtn.style.transform = 'scale(1)';
    lockBtn.style.opacity = '1';
    if (lockProgressFill) lockProgressFill.style.strokeDashoffset = lockMaxOffset;
}

if (lockBtn) {
    lockBtn.style.transition = 'transform 0.2s, opacity 0.2s';
    lockBtn.addEventListener('mousedown', startLockHold);
    lockBtn.addEventListener('mouseup', cancelLockHold);
    lockBtn.addEventListener('mouseleave', cancelLockHold);
    lockBtn.addEventListener('touchstart', startLockHold);
    lockBtn.addEventListener('touchend', cancelLockHold);
    lockBtn.addEventListener('touchcancel', cancelLockHold);
}

// AUTO Button Toggle (5-Second Hold)
const autoBtn = document.getElementById('autoBtn');
const lightSlider = document.getElementById('lightSlider');
const fanSlider = document.getElementById('fanSlider');
const autoProgressFill = document.getElementById('autoProgressFill');

let autoAnimationFrameId;
let autoStartTime;
const autoHoldDuration = 500; // 0.5 seconds
const autoMaxOffset = 78.5;

function toggleAuto() {
    const isActive = autoBtn.classList.toggle('active');
    const isEmergency = emergencyOverlay && emergencyOverlay.classList.contains('active');
    lightSlider.disabled = isEmergency ? true : isActive;
    fanSlider.disabled = isActive;
}

function updateAutoProgress() {
    const elapsed = Date.now() - autoStartTime;
    let progress = Math.min(elapsed / autoHoldDuration, 1);
    
    const currentOffset = autoMaxOffset - (progress * autoMaxOffset);
    if (autoProgressFill) autoProgressFill.style.strokeDashoffset = currentOffset;
    
    if (progress >= 1) {
        toggleAuto();
        resetAutoProgress();
    } else {
        autoAnimationFrameId = requestAnimationFrame(updateAutoProgress);
    }
}

function startAutoHold(e) {
    if (e.type === 'touchstart') e.preventDefault();
    autoBtn.style.transform = 'scale(0.95)';
    autoBtn.style.opacity = '0.9';
    
    autoStartTime = Date.now();
    updateAutoProgress();
}

function cancelAutoHold() {
    cancelAnimationFrame(autoAnimationFrameId);
    resetAutoProgress();
}

function resetAutoProgress() {
    autoBtn.style.transform = 'scale(1)';
    autoBtn.style.opacity = '1';
    if (autoProgressFill) autoProgressFill.style.strokeDashoffset = autoMaxOffset;
}

if (autoBtn) {
    autoBtn.style.transition = 'transform 0.2s, opacity 0.2s';
    autoBtn.addEventListener('mousedown', startAutoHold);
    autoBtn.addEventListener('mouseup', cancelAutoHold);
    autoBtn.addEventListener('mouseleave', cancelAutoHold);
    autoBtn.addEventListener('touchstart', startAutoHold);
    autoBtn.addEventListener('touchend', cancelAutoHold);
    autoBtn.addEventListener('touchcancel', cancelAutoHold);
}

// SOS Button Logic (3 Second Hold)
const sosBtn = document.getElementById('sosBtn');
const sosProgressFill = document.getElementById('sosProgressFill');
const emergencyOverlay = document.getElementById('emergencyOverlay');
const emergencyStatusText = document.getElementById('emergencyStatusText');

let holdTimer;
let animationFrameId;
let startTime;
const holdDuration = 2000; // 2 seconds
const maxOffset = 628; // circumference of circle with r=100

function startHold(e) {
    // Prevent default touch behaviors like scrolling
    if (e.type === 'touchstart') {
        e.preventDefault();
    }
    
    startTime = Date.now();
    updateProgress();
}

function updateProgress() {
    const elapsed = Date.now() - startTime;
    let progress = Math.min(elapsed / holdDuration, 1);
    
    // Update stroke-dashoffset (from 502 down to 0)
    const currentOffset = maxOffset - (progress * maxOffset);
    sosProgressFill.style.strokeDashoffset = currentOffset;
    
    if (progress >= 1) {
        // Hold completed
        triggerEmergencyToggle();
        resetProgress();
    } else {
        animationFrameId = requestAnimationFrame(updateProgress);
    }
}

function cancelHold() {
    cancelAnimationFrame(animationFrameId);
    resetProgress();
}

function resetProgress() {
    sosProgressFill.style.strokeDashoffset = maxOffset;
}

let previousLightValue = 70;

function triggerEmergencyToggle() {
    emergencyOverlay.classList.toggle('active');
    document.body.classList.toggle('emergency-active');
    
    if (emergencyOverlay.classList.contains('active')) {
        emergencyStatusText.innerHTML = `None / <span class="active">SOS</span> / HAZMAT / Medical Emergency`;
        // Auto-unlock door on emergency and disable lock button visually
        isLocked = false;
        if (lockBtn) {
            lockBtn.src = 'assets/Unlocked_Button.png';
            lockBtn.style.opacity = '0.5';
            lockBtn.style.cursor = 'not-allowed';
        }
        // Auto light to 100% and disable manual adjustments
        if (lightSlider) {
            previousLightValue = lightSlider.value;
            lightSlider.value = 100;
            lightSlider.disabled = true;
            updateSliderBackground(lightSlider);
            updateLedStatusText(100);
        }
    } else {
        emergencyStatusText.innerHTML = `<span class="active">None</span> / SOS / HAZMAT / Medical Emergency`;
        if (lockBtn) {
            lockBtn.style.opacity = '1';
            lockBtn.style.cursor = 'pointer';
        }
        // Restore light to previous value and set disabled state based on AUTO active state
        if (lightSlider) {
            lightSlider.value = previousLightValue;
            lightSlider.disabled = autoBtn ? autoBtn.classList.contains('active') : false;
            updateSliderBackground(lightSlider);
            updateLedStatusText(previousLightValue);
        }
    }
}

// Mouse events
sosBtn.addEventListener('mousedown', startHold);
sosBtn.addEventListener('mouseup', cancelHold);
sosBtn.addEventListener('mouseleave', cancelHold);

// Touch events
sosBtn.addEventListener('touchstart', startHold);
sosBtn.addEventListener('touchend', cancelHold);
sosBtn.addEventListener('touchcancel', cancelHold);

// Helper to update LED Brightness status text dynamically
function updateLedStatusText(val) {
    const ledBrightnessOptions = document.querySelector('.current-stats .stat-row .stat-options');
    if (!ledBrightnessOptions) return;
    if (val == 0) {
        ledBrightnessOptions.innerHTML = `<span class="active">Off</span> / Dim / Bright`;
    } else if (val <= 60) {
        ledBrightnessOptions.innerHTML = `Off / <span class="active">Dim</span> / Bright`;
    } else {
        ledBrightnessOptions.innerHTML = `Off / Dim / <span class="active">Bright</span>`;
    }
}

// Helper to update Fan Speed status text dynamically
function updateFanStatusText(val) {
    const fanSpeedOptions = document.querySelectorAll('.current-stats .stat-row .stat-options')[1];
    if (!fanSpeedOptions) return;
    if (val == 0) {
        fanSpeedOptions.innerHTML = `<span class="active">Off</span> / Lv 1 / Lv 2 / Lv 3`;
    } else if (val <= 33) {
        fanSpeedOptions.innerHTML = `Off / <span class="active">Lv 1</span> / Lv 2 / Lv 3`;
    } else if (val <= 66) {
        fanSpeedOptions.innerHTML = `Off / Lv 1 / <span class="active">Lv 2</span> / Lv 3`;
    } else {
        fanSpeedOptions.innerHTML = `Off / Lv 1 / Lv 2 / <span class="active">Lv 3</span>`;
    }
}

// Custom slider backgrounds to show fill level (Optional Enhancement)
const sliders = document.querySelectorAll('.custom-slider');
function updateSliderBackground(slider) {
    const min = slider.min || 0;
    const max = slider.max || 100;
    const value = slider.value;
    const percentage = ((value - min) / (max - min)) * 100;
    slider.style.setProperty('--value', `${percentage}%`);
    slider.style.setProperty('--value-num', percentage);
}

sliders.forEach(slider => {
    updateSliderBackground(slider);
    slider.addEventListener('input', (e) => {
        updateSliderBackground(e.target);
        if (e.target.id === 'lightSlider') {
            updateLedStatusText(e.target.value);
        } else if (e.target.id === 'fanSlider') {
            updateFanStatusText(e.target.value);
        }
    });
});

// Register Service Worker for PWA (Progressive Web App)
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('./sw.js')
            .then(registration => {
                console.log('MediGuard Service Worker registered successfully with scope:', registration.scope);
            })
            .catch(error => {
                console.error('MediGuard Service Worker registration failed:', error);
            });
    });
}
