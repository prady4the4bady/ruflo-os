import SwiftUI

@main
struct RufloDesktop: App {
    @State private var agentStatus: AgentStatus = .idle

    var body: some Scene {
        WindowGroup {
            DesktopView(agentStatus: $agentStatus)
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1920, height: 1080)
    }
}

struct DesktopView: View {
    @Binding var agentStatus: AgentStatus

    var body: some View {
        ZStack {
            // Wallpaper
            Image("wallpaper_default")
                .resizable()
                .ignoresSafeArea()

            // Dock
            DocketView()
                .position(x: UIScreen.main.bounds.width/2, y: UIScreen.main.bounds.height - 50)

            // Menu Bar
            MenuBarView(agentStatus: $agentStatus)
                .position(x: UIScreen.main.bounds.width/2, y: 14)

            // Agent Monitor overlay (when active)
            if agentStatus == .running {
                AgentMonitorView()
            }
        }
    }
}

enum AgentStatus {
    case idle, running, paused, error
}