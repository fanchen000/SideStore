import Foundation

func require(_ valid: @autoclosure () -> Bool, _ message: String) {
    if !valid() {
        fputs("FAIL: \(message)\n", stderr)
        exit(1)
    }
}

let original = "com.example.tool.xctrunner"
let signed = original + ".PERSONALTEAM"
let root = FileManager.default.temporaryDirectory
    .appendingPathComponent("NestedXCTestGuard-\(UUID().uuidString)", isDirectory: true)
defer { try? FileManager.default.removeItem(at: root) }

func mockApp(testIdentifier: String?) throws -> URL {
    let app = root.appendingPathComponent(UUID().uuidString).appendingPathComponent("Example.app")
    let plugins = app.appendingPathComponent("PlugIns")
    try FileManager.default.createDirectory(at: plugins, withIntermediateDirectories: true)
    if let id = testIdentifier {
        let test = plugins.appendingPathComponent("iCTRLUITests.xctest")
        try FileManager.default.createDirectory(
            at: test.appendingPathComponent("_CodeSignature"), withIntermediateDirectories: true
        )
        let properties = ["CFBundleIdentifier": id, "CFBundleExecutable": "iCTRLUITests"]
        let data = try PropertyListSerialization.data(
            fromPropertyList: properties, format: .binary, options: 0
        )
        try data.write(to: test.appendingPathComponent("Info.plist"), options: .atomic)
        try Data("stale".utf8).write(
            to: test.appendingPathComponent("_CodeSignature/CodeResources")
        )
    }
    return app
}

func testIdentifier(at app: URL) throws -> String {
    let data = try Data(contentsOf: app.appendingPathComponent("PlugIns/iCTRLUITests.xctest/Info.plist"))
    let info = try PropertyListSerialization.propertyList(
        from: data, options: [], format: nil
    ) as! [String: Any]
    return info["CFBundleIdentifier"] as! String
}

do {
    let test = try mockApp(testIdentifier: original)
    let changed = try NestedXCTestBundleID.reconcile(
        stagedApp: test, originalBundleID: original, signedBundleID: signed
    )
    require(changed == 1, "must reconcile nested xctest bundle identifier")
    let changedIdentity = try testIdentifier(at: test)
    require(changedIdentity == signed, "nested ID must equal signed outer ID")
    require(!FileManager.default.fileExists(
        atPath: test.appendingPathComponent(
            "PlugIns/iCTRLUITests.xctest/_CodeSignature"
        ).path
    ), "old nested signature must be invalidated in temporary staging")

    let unchanged = try NestedXCTestBundleID.reconcile(
        stagedApp: test, originalBundleID: original, signedBundleID: signed
    )
    require(unchanged == 0, "must be idempotent for already-correct nested bundle")

    do {
        try NestedXCTestBundleID.requireSignedArtifacts(stagedApp: test, signedBundleID: signed)
        require(false, "must not accept missing signatures and executable")
    } catch NestedXCTestBundleID.ReconcileError.missingSignedTestArtifacts {
        // Expected: the fixture is only metadata-aligned, not signed.
    }
    let testDir = test.appendingPathComponent("PlugIns/iCTRLUITests.xctest")
    try Data("synthetic fixture binary".utf8).write(to: testDir.appendingPathComponent("iCTRLUITests"))
    try FileManager.default.createDirectory(
        at: testDir.appendingPathComponent("_CodeSignature"), withIntermediateDirectories: true
    )
    try Data("synthetic fixture resources".utf8).write(
        to: testDir.appendingPathComponent("_CodeSignature/CodeResources")
    )
    try NestedXCTestBundleID.requireSignedArtifacts(stagedApp: test, signedBundleID: signed)
    do {
        try NestedXCTestBundleID.requireSignedArtifacts(stagedApp: test, signedBundleID: original)
        require(false, "must reject an unintended nested bundle identifier")
    } catch NestedXCTestBundleID.ReconcileError.unexpectedNestedIdentifier {
        // Expected: signed nested and outer IDs must remain identical.
    }
    try FileManager.default.removeItem(at: testDir.appendingPathComponent("iCTRLUITests"))
    do {
        try NestedXCTestBundleID.requireSignedArtifacts(stagedApp: test, signedBundleID: signed)
        require(false, "must reject a signed-looking test with missing executable")
    } catch NestedXCTestBundleID.ReconcileError.missingSignedTestArtifacts {
        // Expected: a signature directory alone does not make XCTest launchable.
    }

    let unrelated = try mockApp(testIdentifier: "com.different.test")
    do {
        _ = try NestedXCTestBundleID.reconcile(
            stagedApp: unrelated, originalBundleID: original, signedBundleID: signed
        )
        require(false, "unrelated nested XCTest ID must not be rewritten")
    } catch NestedXCTestBundleID.ReconcileError.unexpectedNestedIdentifier {
        let stillUnrelated = try testIdentifier(at: unrelated)
        require(stillUnrelated == "com.different.test",
                "unexpected nested ID must remain unchanged")
    }

    let ordinary = try mockApp(testIdentifier: nil)
    let noXCTest = try NestedXCTestBundleID.reconcile(
        stagedApp: ordinary, originalBundleID: original, signedBundleID: signed
    )
    require(noXCTest == 0, "ordinary applications without XCTest must remain untouched")

    print("NESTED_XCTEST_IDENTITY_AND_ARTIFACT_REGRESSION_8_OF_8_PASS")
} catch {
    fputs("FAIL: test threw \(type(of: error))\n", stderr)
    exit(1)
}
