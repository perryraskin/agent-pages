import SwiftUI

struct MessageEntryView: View {
    @ObservedObject var store: PageStore
    @ObservedObject var entry: MessageEntry
    var insertPage: (Page) -> Void
    var expand: () -> Void

    var body: some View {
        Group {
            switch entry.route {
            case .waiting:
                PageLoadingPlaceholder()
                    .accessibilityIdentifier("message-entry-loading")
            case .library:
                LibraryView(store: store, insertPage: insertPage, expand: expand)
            case .page(let page):
                NavigationStack {
                    PageDetail(store: store, page: page, insertPage: insertPage)
                        .id(entry.generation)
                        .toolbar {
                            ToolbarItem(placement: .topBarLeading) {
                                Button {
                                    store.selected = nil
                                    entry.showLibrary()
                                } label: { Image(systemName: "square.grid.2x2") }
                                    .accessibilityLabel("All Pages")
                            }
                        }
                }.tint(.hermes).foregroundStyle(Color.pageInk)
            case .invalid:
                VStack(spacing: 20) {
                    ContentUnavailableView("Couldn’t open this card", systemImage: "doc.questionmark",
                        description: Text("This card does not contain a valid private Hermes Page link."))
                    Button("All Pages") { store.selected = nil; entry.showLibrary() }
                        .buttonStyle(.borderedProminent)
                }.background(Color.paper)
            }
        }
    }
}

struct LibraryView: View {
    @ObservedObject var store: PageStore
    var insertPage: ((Page) -> Void)? = nil
    var expand: (() -> Void)? = nil
    @State private var query = ""
    @State private var onlyFavorites = false
    @State private var settings = false
    @State private var selectedTag: String?

    var filtered: [Page] {
        store.pages.filter {
            (!onlyFavorites || store.favorites.contains($0.id)) &&
            $0.matches(query: query, tag: selectedTag)
        }
    }
    var tagCounts: [(tag: String, count: Int)] {
        Dictionary(grouping: store.pages.flatMap(\.tags), by: { $0 })
            .map { (tag: $0.key, count: $0.value.count) }.sorted { $0.tag < $1.tag }
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    VStack(spacing: 9) {
                        Text("Hermes")
                            .font(.custom("InstrumentSerif-Regular", size: 52, relativeTo: .largeTitle))
                            .tracking(-1.2).foregroundStyle(Color.pageInk)
                        Text("Your Pages, thoughtfully kept.")
                            .font(.custom("InstrumentSerif-Regular", size: 23, relativeTo: .title3))
                            .foregroundStyle(Color.secondaryInk)
                    }.frame(maxWidth: .infinity).padding(.top, 22).padding(.bottom, 12)
                    HStack {
                        Image(systemName: "magnifyingglass").foregroundStyle(Color.secondaryInk)
                        TextField("Find a Page or tag", text: $query).accessibilityIdentifier("pageSearch")
                            .onTapGesture { expand?() }
                        if !query.isEmpty { Button { query = "" } label: { Image(systemName: "xmark.circle.fill") }.foregroundStyle(Color.secondaryInk) }
                    }.padding(13).background(Color.pageSurface, in: RoundedRectangle(cornerRadius: 13))
                    HStack(spacing: 12) {
                        Menu {
                            Button("All tags", systemImage: selectedTag == nil ? "checkmark" : "tag") { selectedTag = nil }
                            ForEach(tagCounts, id: \.tag) { item in
                                Button {
                                    expand?(); selectedTag = item.tag
                                } label: {
                                    if selectedTag == item.tag {
                                        Label("\(item.tag) (\(item.count))", systemImage: "checkmark")
                                    } else { Text("\(item.tag) (\(item.count))") }
                                }
                            }
                        } label: {
                            Label("Tags", systemImage: "tag").font(.caption.weight(.medium))
                        }.accessibilityIdentifier("tag-filter-menu").accessibilityLabel("Filter by tag")
                        if let selectedTag {
                            Button { self.selectedTag = nil } label: {
                                HStack(spacing: 5) {
                                    Text(selectedTag).lineLimit(1)
                                    Image(systemName: "xmark.circle.fill")
                                }.font(.caption).padding(.horizontal, 9).padding(.vertical, 6)
                                    .background(Color.hermes.opacity(0.1), in: Capsule())
                            }.accessibilityLabel("Clear tag filter: \(selectedTag)")
                                .accessibilityIdentifier("clear-tag-filter")
                        }
                        Spacer(minLength: 0)
                        Text("\(filtered.count) Page\(filtered.count == 1 ? "" : "s")")
                            .font(.caption).foregroundStyle(Color.secondaryInk)
                    }
                    HStack {
                        Text(onlyFavorites ? "Favorites" : "Your Pages").font(.system(size: 12, weight: .medium)).tracking(0.5).foregroundStyle(Color.secondaryInk)
                        Spacer()
                        Button { onlyFavorites.toggle() } label: {
                            Label(onlyFavorites ? "Show all" : "Favorites", systemImage: onlyFavorites ? "square.grid.2x2" : "star")
                                .font(.caption.weight(.medium))
                        }
                    }
                    if store.loading && store.pages.isEmpty {
                        ProgressView("Opening your library…").frame(maxWidth: .infinity).padding(28)
                    } else if let error = store.error {
                        VStack(alignment: .leading, spacing: 12) {
                            Label("Library unavailable", systemImage: "network.slash").font(.headline)
                            Text(error).font(.footnote).foregroundStyle(Color.secondaryInk)
                            Button("Try again") { Task { await store.retry() } }.buttonStyle(.borderedProminent)
                        }.padding(20).frame(maxWidth: .infinity, alignment: .leading).background(Color.pageSurface, in: RoundedRectangle(cornerRadius: 17))
                    } else if filtered.isEmpty {
                        ContentUnavailableView(onlyFavorites ? "No favorites yet" : "No matching Pages", systemImage: "doc.text.magnifyingglass", description: Text("Try another search or clear your filters."))
                        if selectedTag != nil || !query.isEmpty || onlyFavorites {
                            Button("Clear filters") { selectedTag = nil; query = ""; onlyFavorites = false }
                                .font(.subheadline.weight(.medium)).frame(maxWidth: .infinity)
                        }
                    } else {
                        LazyVStack(spacing: 10) {
                            ForEach(filtered) { page in
                                Button { expand?(); store.selected = page } label: {
                                    HStack(spacing: 14) {
                                        Image(systemName: "doc.text").font(.system(size: 21, weight: .light)).foregroundStyle(Color.hermes)
                                            .frame(width: 44, height: 54).background(Color.hermes.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
                                        VStack(alignment: .leading, spacing: 7) {
                                            Text(page.title).font(.custom("InstrumentSerif-Regular", size: 25, relativeTo: .title3)).foregroundStyle(Color.pageInk).multilineTextAlignment(.leading)
                                            HStack(spacing: 6) {
                                                if let date = page.date { Text(date, style: .date) }
                                                if page.automatic { Text("· Auto") }
                                                if store.favorites.contains(page.id) { Image(systemName: "star.fill").font(.system(size: 9)) }
                                            }.font(.caption).foregroundStyle(Color.secondaryInk)
                                            if !page.tags.isEmpty { PageTagChips(tags: page.tags) }
                                        }
                                        Spacer(minLength: 0)
                                        Image(systemName: "chevron.right").font(.caption.weight(.bold)).foregroundStyle(.tertiary)
                                    }.padding(14).background(Color.pageSurface, in: RoundedRectangle(cornerRadius: 19))
                                }.buttonStyle(.plain).accessibilityIdentifier("page-\(page.id)")
                                .contextMenu {
                                    Button(store.favorites.contains(page.id) ? "Remove favorite" : "Add favorite", systemImage: "star") { store.toggleFavorite(page) }
                                    if let insertPage { Button("Insert private Page card", systemImage: "message") { insertPage(page) } }
                                }
                            }
                        }
                    }
                    Label("Private unless you choose to share.", systemImage: "lock")
                        .font(.caption2).foregroundStyle(Color.secondaryInk).frame(maxWidth: .infinity).padding(.bottom, 20)
                }.padding(.horizontal, 20)
            }.background(Color.paper).refreshable { await store.refresh() }
            .navigationTitle("Hermes Pages").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { expand?(); settings = true } label: { Image(systemName: "slider.horizontal.3") }.accessibilityLabel("Settings")
                }
            }
            .navigationDestination(item: $store.selected) { page in
                PageDetail(store: store, page: page, insertPage: insertPage)
                    .id(store.readerGeneration)
            }
            .sheet(isPresented: $settings) { SettingsView(store: store) }
            .task { if store.pages.isEmpty { await store.refresh() } }
        }.tint(.hermes).foregroundStyle(Color.pageInk)
    }
}

struct SettingsView: View {
    @ObservedObject var store: PageStore
    @Environment(\.dismiss) var dismiss
    @State private var endpoint = ""
    @State private var error: String?
    var body: some View {
        NavigationStack {
            Form {
                Section("Private connection") {
                    TextField("HTTPS server", text: $endpoint).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    Text("Your iPhone and Mac must be connected to Tailscale. This address is shared with the Messages extension through an App Group.").font(.footnote).foregroundStyle(Color.secondaryInk)
                    Button("Save and reconnect") {
                        guard let url = URL(string: endpoint), url.scheme == "https", url.host != nil,
                              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
                              url.path.isEmpty || url.path == "/" else { error = "Enter an HTTPS origin without a path, credentials, or query."; return }
                        store.server = endpoint.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                        Task { await store.refresh(); if store.error == nil { dismiss() } }
                    }
                    if let error { Text(error).foregroundStyle(.red) }
                }
                Section("Sharing") {
                    NavigationLink("Manage shared snapshots") { SharesView(store: store) }
                    Text("Only Pages you explicitly share become available outside your tailnet. Anyone with a share link can read that frozen snapshot until you revoke it or it expires.").font(.footnote).foregroundStyle(Color.secondaryInk)
                }
                Section("In Messages") {
                    Text("Open + in a conversation, choose More, then Hermes Pages. Select a Page and insert its private card. The recipient needs Hermes Pages and access to your tailnet. Use a share link instead for other people.").font(.footnote)
                }
            }.navigationTitle("Settings").navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
                .onAppear { endpoint = store.server }
        }
    }
}

struct SharesView: View {
    @ObservedObject var store: PageStore
    @State var error: String?
    @State var pending: SharedPage?
    var body: some View {
        List {
            if let error { Text(error).foregroundStyle(.red) }
            if store.shares.isEmpty { Text("No shared snapshots yet.").foregroundStyle(Color.secondaryInk) }
            ForEach(store.shares) { share in
                VStack(alignment: .leading, spacing: 7) {
                    Text(share.title).font(.headline)
                    Text(share.active ? "Expires \(Date(timeIntervalSince1970: share.expires).formatted(date: .abbreviated, time: .shortened))" : "Expired or revoked")
                        .font(.caption).foregroundStyle(Color.secondaryInk)
                    if share.active { Button("Revoke access", role: .destructive) { pending = share } }
                }.padding(.vertical, 5)
            }
        }.navigationTitle("Shared snapshots")
            .task { do { try await store.loadShares() } catch { self.error = error.localizedDescription } }
            .alert("Revoke this link?", isPresented: Binding(get: { pending != nil }, set: { if !$0 { pending = nil } })) {
                Button("Cancel", role: .cancel) { pending = nil }
                Button("Revoke", role: .destructive) {
                    if let share = pending { Task { do { try await store.revoke(share) } catch { self.error = error.localizedDescription } } }
                    pending = nil
                }
            } message: { Text("The link will stop opening. Already downloaded copies cannot be recalled.") }
    }
}


struct PageTagChips: View {
    let tags: [String]
    var body: some View {
        TagFlowLayout(spacing: 6) {
            ForEach(tags, id: \.self) { tag in
                Text(tag).font(.caption2.weight(.medium)).foregroundStyle(Color.hermes)
                    .lineLimit(1).padding(.horizontal, 8).padding(.vertical, 4)
                    .background(Color.hermes.opacity(0.09), in: Capsule())
                    .accessibilityLabel("Tag: \(tag)")
            }
        }.accessibilityIdentifier("page-tags")
    }
}

struct TagFlowLayout: Layout {
    var spacing: CGFloat = 6
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(width: proposal.width, subviews: subviews).size
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrange(width: bounds.width, subviews: subviews)
        for (index, frame) in result.frames.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                                  proposal: ProposedViewSize(frame.size))
        }
    }
    private func arrange(width: CGFloat?, subviews: Subviews) -> (size: CGSize, frames: [CGRect]) {
        let available = max(1, width ?? subviews.reduce(0) { $0 + $1.sizeThatFits(.unspecified).width + spacing })
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0
        var frames: [CGRect] = []
        for view in subviews {
            let size = view.sizeThatFits(ProposedViewSize(width: available, height: nil))
            if x > 0 && x + size.width > available { x = 0; y += rowHeight + spacing; rowHeight = 0 }
            frames.append(CGRect(origin: CGPoint(x: x, y: y), size: size))
            x += size.width + spacing; rowHeight = max(rowHeight, size.height)
        }
        return (CGSize(width: available, height: y + rowHeight), frames)
    }
}
