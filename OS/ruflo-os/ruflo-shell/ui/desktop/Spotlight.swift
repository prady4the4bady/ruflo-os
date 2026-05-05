import SwiftUI

struct SpotlightView: View {
    @State private var query = ""
    @State private var isExpanded = false
    @FocusState private var isFocused: Bool

    var body: some View {
        VStack {
            if isExpanded {
                // Full Spotlight overlay
                ZStack {
                    Color.black.opacity(0.3)
                        .ignoresSafeArea()
                        .onTapGesture { isExpanded = false }

                    VStack {
                        HStack {
                            Image(systemName: "magnifyingglass")
                            TextField("Search for apps, files, or ask Ruflo...", text: $query)
                                .focused($isFocused)
                                .font(.system(size: 16))
                                .onSubmit { submitToRuflo() }
                        }
                        .padding()
                        .background(.ultraThinMaterial)
                        .cornerRadius(12)
                        .frame(width: 600)

                        // Live Ruflo preview
                        if !query.isEmpty {
                            RufloPreviewView(query: query)
                                .frame(width: 600)
                        }
                    }
                }
                .onAppear { isFocused = true }
            }
        }
        .globalKeyboardShortcut(.init(" "), modifiers: .command) {
            isExpanded.toggle()
        }
    }

    func submitToRuflo() {
        // Send query to Ruflo Agent
        print("Ruflo task: \(query)")
        isExpanded = false
        query = ""
    }
}

struct RufloPreviewView: View {
    let query: String
    @State private var preview = "Ruflo will search the web and summarize..."

    var body: some View {
        Text(preview)
            .font(.system(size: 14))
            .foregroundColor(.secondary)
            .padding()
            .frame(width: 600, alignment: .leading)
            .background(.ultraThinMaterial)
            .cornerRadius(12)
    }
}