import SwiftUI

struct MenuBarView: View {
    @Binding var agentStatus: AgentStatus

    var body: some View {
        HStack {
            // Left: Ruflo logo + app menus
            HStack(spacing: 12) {
                Image("ruflo-logo")
                    .resizable()
                    .frame(width: 16, height: 16)
                Text("File").font(.system(size: 13))
                Text("Edit").font(.system(size: 13))
                Text("View").font(.system(size: 13))
            }

            Spacer()

            // Right: System tray + agent status
            HStack(spacing: 16) {
                AgentStatusDot(status: agentStatus)
                Text(Date(), style: .time)
                    .font(.system(size: 12))
            }
        }
        .padding(.horizontal, 12)
        .frame(height: 28)
        .background(.ultraThinMaterial)
    }
}

struct AgentStatusDot: View {
    let status: AgentStatus

    var color: Color {
        switch status {
        case .idle: return .gray
        case .running: return .green
        case .paused: return .orange
        case .error: return .red
        }
    }

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 8, height: 8)
    }
}