import Foundation

/// Keep XCTest's nested test bundle identity in lockstep with the signed
/// outer Runner identity before CodeSignKit recursively signs the bundles.
///
/// Only operates on a freshly copied, temporary app staged for signing.
/// Existing installed app data and its original IPA are never modified.
enum NestedXCTestBundleID {
    enum ReconcileError: Error {
        case unexpectedNestedIdentifier
        case missingNestedIdentifier
        case symlinkedTestBundle
        case missingSignedTestArtifacts
    }

    @discardableResult
    static func reconcile(
        stagedApp: URL,
        originalBundleID: String,
        signedBundleID: String,
        fileManager: FileManager = .default
    ) throws -> Int {
        guard !originalBundleID.isEmpty, !signedBundleID.isEmpty else {
            throw ReconcileError.missingNestedIdentifier
        }
        let plugIns = stagedApp.appendingPathComponent("PlugIns", isDirectory: true)
        var isDirectory: ObjCBool = false
        guard fileManager.fileExists(atPath: plugIns.path, isDirectory: &isDirectory),
              isDirectory.boolValue else { return 0 }

        let items = try fileManager.contentsOfDirectory(
            at: plugIns,
            includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey],
            options: [.skipsHiddenFiles]
        )
        var updated = 0
        for bundle in items where bundle.pathExtension.lowercased() == "xctest" {
            let flags = try bundle.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
            guard flags.isSymbolicLink != true, flags.isDirectory == true else {
                throw ReconcileError.symlinkedTestBundle
            }

            let infoURL = bundle.appendingPathComponent("Info.plist")
            let raw = try Data(contentsOf: infoURL)
            var format = PropertyListSerialization.PropertyListFormat.xml
            guard var plist = try PropertyListSerialization.propertyList(
                from: raw, options: [], format: &format
            ) as? [String: Any],
                  let current = plist["CFBundleIdentifier"] as? String,
                  !current.isEmpty else {
                throw ReconcileError.missingNestedIdentifier
            }
            // Never silently rewrite unrelated XCTest identities.
            guard current == originalBundleID || current == signedBundleID else {
                throw ReconcileError.unexpectedNestedIdentifier
            }
            guard current != signedBundleID else { continue }

            plist["CFBundleIdentifier"] = signedBundleID
            let modified = try PropertyListSerialization.data(
                fromPropertyList: plist, format: format, options: 0
            )
            try modified.write(to: infoURL, options: .atomic)
            let oldSignature = bundle.appendingPathComponent("_CodeSignature", isDirectory: true)
            if fileManager.fileExists(atPath: oldSignature.path) {
                try fileManager.removeItem(at: oldSignature)
            }
            updated += 1
        }
        return updated
    }

    /// Reject an XCTest Runner before installation when recursive signing
    /// omitted the nested test binary or bundle resources. CodeSignKit still
    /// owns cryptographic signature verification.
    static func requireSignedArtifacts(
        stagedApp: URL,
        signedBundleID: String,
        fileManager: FileManager = .default
    ) throws {
        guard !signedBundleID.isEmpty else {
            throw ReconcileError.missingNestedIdentifier
        }
        let plugIns = stagedApp.appendingPathComponent("PlugIns", isDirectory: true)
        guard fileManager.fileExists(atPath: plugIns.path) else { return }
        let items = try fileManager.contentsOfDirectory(
            at: plugIns,
            includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey],
            options: [.skipsHiddenFiles]
        )
        for bundle in items where bundle.pathExtension.lowercased() == "xctest" {
            let flags = try bundle.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
            guard flags.isSymbolicLink != true, flags.isDirectory == true else {
                throw ReconcileError.symlinkedTestBundle
            }
            let info = try Data(contentsOf: bundle.appendingPathComponent("Info.plist"))
            guard let plist = try PropertyListSerialization.propertyList(
                from: info, options: [], format: nil
            ) as? [String: Any],
                  let testID = plist["CFBundleIdentifier"] as? String,
                  testID == signedBundleID,
                  let executableName = plist["CFBundleExecutable"] as? String,
                  !executableName.isEmpty,
                  !executableName.contains("/"),
                  executableName != "." && executableName != ".." else {
                throw ReconcileError.unexpectedNestedIdentifier
            }
            let binary = bundle.appendingPathComponent(executableName)
            let resources = bundle.appendingPathComponent("_CodeSignature/CodeResources")
            let binaryFlags = try? binary.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            let resourceFlags = try? resources.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            guard binaryFlags?.isRegularFile == true,
                  binaryFlags?.isSymbolicLink != true,
                  (binaryFlags?.fileSize ?? 0) > 0,
                  resourceFlags?.isRegularFile == true,
                  resourceFlags?.isSymbolicLink != true,
                  (resourceFlags?.fileSize ?? 0) > 0 else {
                throw ReconcileError.missingSignedTestArtifacts
            }
        }
    }
}
