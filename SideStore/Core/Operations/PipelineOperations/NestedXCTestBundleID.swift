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

    /// Remember the test-bundle count before the signer touches the staged app.
    /// A signer that drops PlugIns/*.xctest must never look successful.
    static func countTestBundles(
        stagedApp: URL,
        fileManager: FileManager = .default
    ) throws -> Int {
        let plugIns = stagedApp.appendingPathComponent("PlugIns", isDirectory: true)
        var isDirectory: ObjCBool = false
        guard fileManager.fileExists(atPath: plugIns.path, isDirectory: &isDirectory),
              isDirectory.boolValue else { return 0 }
        let items = try fileManager.contentsOfDirectory(
            at: plugIns,
            includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey],
            options: [.skipsHiddenFiles]
        )
        var count = 0
        for bundle in items where bundle.pathExtension.lowercased() == "xctest" {
            let flags = try bundle.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
            guard flags.isSymbolicLink != true, flags.isDirectory == true else {
                throw ReconcileError.symlinkedTestBundle
            }
            count += 1
        }
        return count
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

    /// An offline post-sign structural gate, not cryptographic verification.
    /// iOS/testmanagerd remains the authority on actual signature validity.
    /// Fail closed if the signer discarded or failed to sign a nested XCTest.
    @discardableResult
    static func requireSignedArtifacts(
        stagedApp: URL,
        expectedTestCount: Int,
        fileManager: FileManager = .default
    ) throws -> Int {
        guard expectedTestCount >= 0 else {
            throw ReconcileError.missingSignedTestArtifacts
        }
        let plugIns = stagedApp.appendingPathComponent("PlugIns", isDirectory: true)
        var isDirectory: ObjCBool = false
        guard fileManager.fileExists(atPath: plugIns.path, isDirectory: &isDirectory),
              isDirectory.boolValue else {
            guard expectedTestCount == 0 else {
                throw ReconcileError.missingSignedTestArtifacts
            }
            return 0
        }

        let items = try fileManager.contentsOfDirectory(
            at: plugIns,
            includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey],
            options: [.skipsHiddenFiles]
        )
        var verified = 0
        for bundle in items where bundle.pathExtension.lowercased() == "xctest" {
            let flags = try bundle.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
            guard flags.isSymbolicLink != true, flags.isDirectory == true else {
                throw ReconcileError.symlinkedTestBundle
            }
            let infoURL = bundle.appendingPathComponent("Info.plist")
            let raw = try Data(contentsOf: infoURL)
            guard let info = try PropertyListSerialization.propertyList(
                from: raw, options: [], format: nil
            ) as? [String: Any],
                  let executable = info["CFBundleExecutable"] as? String,
                  !executable.isEmpty,
                  !executable.contains("/"), !executable.contains("\\"),
                  executable != ".", executable != ".." else {
                throw ReconcileError.missingSignedTestArtifacts
            }
            let executableURL = bundle.appendingPathComponent(executable)
            let sealURL = bundle.appendingPathComponent("_CodeSignature/CodeResources")
            guard fileManager.fileExists(atPath: executableURL.path),
                  fileManager.fileExists(atPath: sealURL.path),
                  let binaryBytes = try? executableURL.resourceValues(forKeys: [.fileSizeKey]).fileSize,
                  let sealBytes = try? sealURL.resourceValues(forKeys: [.fileSizeKey]).fileSize,
                  binaryBytes > 4096, sealBytes > 0 else {
                throw ReconcileError.missingSignedTestArtifacts
            }
            verified += 1
        }
        guard verified == expectedTestCount else {
            throw ReconcileError.missingSignedTestArtifacts
        }
        return verified
    }
}
