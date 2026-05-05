// ─────────────────────────────────────────────────────────────
// Ruflo OS Dock Panel Configuration
// KDE Plasma 6 panel script for macOS-style dock
// ─────────────────────────────────────────────────────────────
// Usage: plasma-apply-wallpaperimage <wallpaper> && \
//        qdbus org.kde.plasmashell /PlasmaShell evaluateScript "$(cat dock/panel-config.js)"

// Remove default bottom panel if it exists
var panels = panels();
for (var i = 0; i < panels.length; i++) {
    if (panels[i].location === "bottom") {
        panels[i].remove();
    }
}

// ── Create macOS-style Dock (bottom panel) ──────────────────
var dock = new Panel("dock");
dock.location = "bottom";
dock.height = Math.round(gridUnit * 3.5);
dock.alignment = "center";
dock.hiding = "dodgewindows";   // Auto-hide when windows overlap
dock.floating = true;           // Floating panel (Plasma 6)
dock.lengthMode = "fit";        // Fit content width

// Add icon-only task manager (dock behavior)
var taskManager = dock.addWidget("org.kde.plasma.icontasks");
taskManager.currentConfigGroup = ["General"];
taskManager.writeConfig("launchers", [
    "applications:org.kde.dolphin.desktop",
    "applications:org.kde.konsole.desktop",
    "applications:firefox.desktop",
    "applications:org.kde.kate.desktop",
    "applications:systemsettings.desktop",
]);
taskManager.writeConfig("showOnlyCurrentDesktop", false);
taskManager.writeConfig("showOnlyCurrentActivity", false);
taskManager.writeConfig("indicateAudioStreams", true);
taskManager.writeConfig("maxStripes", 1);

// ── Create macOS-style Top Bar ──────────────────────────────
var topBar = new Panel("topbar");
topBar.location = "top";
topBar.height = Math.round(gridUnit * 1.8);
topBar.alignment = "fill";
topBar.floating = false;

// Left: App Menu (global menu)
var appMenu = topBar.addWidget("org.kde.plasma.appmenu");

topBar.addWidget("org.kde.plasma.panelspacer");

// Center: Digital Clock
var clock = topBar.addWidget("org.kde.plasma.digitalclock");
clock.currentConfigGroup = ["Appearance"];
clock.writeConfig("showDate", true);
clock.writeConfig("dateFormat", "shortDate");
clock.writeConfig("use24hFormat", 2);

topBar.addWidget("org.kde.plasma.panelspacer");

// Right: System tray
var tray = topBar.addWidget("org.kde.plasma.systemtray");

// Right: Notifications
topBar.addWidget("org.kde.plasma.notifications");
