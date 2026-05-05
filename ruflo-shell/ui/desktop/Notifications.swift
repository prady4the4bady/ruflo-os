import SwiftUI

struct NotificationsView: View {
    @State private var notifications: [RufloNotification] = []

    var body: some View {
        VStack(spacing: 8) {
            ForEach(notifications) { notif in
                NotificationBubble(notification: notif)
            }
        }
        .frame(width: 300, alignment: .topTrailing)
        .padding()
    }
}

struct NotificationBubble: View {
    let notification: RufloNotification

    var body: some View {
        HStack {
            Image(systemName: notification.icon)
            VStack(alignment: .leading) {
                Text(notification.title).font(.headline)
                Text(notification.message).font(.caption).foregroundColor(.secondary)
            }
            Spacer()
        }
        .padding()
        .background(.ultraThinMaterial)
        .cornerRadius(12)
    }
}

struct RufloNotification: Identifiable {
    let id = UUID()
    let title: String
    let message: String
    let icon: String
}