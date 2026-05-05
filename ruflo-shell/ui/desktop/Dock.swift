import SwiftUI

struct DockView: View {
    @State private var apps: [DockApp] = [
        DockApp(id: "finder", name: "Finder", icon: "finder", path: "/Applications/Finder.app"),
        DockApp(id: "safari", name: "Safari", icon: "safari", path: "/Applications/Safari.app"),
        DockApp(id: "mail", name: "Mail", icon: "mail", path: "/Applications/Mail.app"),
        DockApp(id: "terminal", name: "Terminal", icon: "terminal", path: "/Applications/Utilities/Terminal.app"),
        DockApp(id: "ruflo-agent", name: "Ruflo Agent", icon: "ruflo", path: "/Applications/RufloAgent.app")
    ]

    var body: some View {
        HStack(spacing: 8) {
            ForEach(apps) { app in
                DockItemView(app: app)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.ultraThinMaterial)
        .cornerRadius(16)
        .shadow(radius: 8)
    }
}

struct DockItemView: View {
    let app: DockApp
    @State private var isHovered = false

    var body: some View {
        Image(app.icon)
            .resizable()
            .frame(width: 48, height: 48)
            .scaleEffect(isHovered ? 1.2 : 1.0)
            .animation(.spring(response: 0.3), value: isHovered)
            .onHover { hovering in
                isHovered = hovering
            }
            .contextMenu {
                Button("Ask Ruflo") {
                    // Trigger Ruflo task for this app
                }
            }
    }
}

struct DockApp: Identifiable {
    let id: String
    let name: String
    let icon: String
    let path: String
}