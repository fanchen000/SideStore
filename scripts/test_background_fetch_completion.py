#!/usr/bin/env python3
"""Compile the real AppDelegate background-fetch method against Swift mocks.

Runs only on macOS Swift (CI). Never accesses device, Apple ID or signing data.
"""
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
code = (ROOT / "AltStore" / "AppDelegate.swift").read_text(encoding="utf8")
start = code.index("    func performBackgroundFetch(backgroundFetchCompletionHandler:")
marker = "\n    }\n}\n\nprivate extension AppDelegate"
end = code.index(marker, start) + len("\n    }")
method = code[start:end]

stub = r"""
import Foundation
struct Source: Hashable {}
struct InstalledApp {
    static func fetchAppsForBackgroundRefresh(in context: Int) -> [InstalledApp] { [InstalledApp()] }
}
struct PersistentContainer { func newBackgroundContext() -> Int { 1 } }
final class DatabaseManager {
    static let shared = DatabaseManager()
    let persistentContainer = PersistentContainer()
}
extension UserDefaults {
    var isBackgroundRefreshEnabled: Bool {
        get { bool(forKey: "prephone.offline.background.enabled") }
        set { set(newValue, forKey: "prephone.offline.background.enabled") }
    }
}
enum UIBackgroundFetchResult: Equatable { case failed, newData, noData }
struct TestError: Error {}
final class AppManager {
    static let shared = AppManager()
    var pending: ((Result<[String: Result<InstalledApp, Error>], Error>) -> Void)?
    var shouldThrow = false
    func backgroundRefresh(_ apps: [InstalledApp],
                           completionHandler: @escaping (Result<[String: Result<InstalledApp, Error>], Error>) -> Void
    ) throws -> Int {
        if shouldThrow { throw TestError() }
        pending = completionHandler
        return 1
    }
}
final class AppDelegate {
    var sourceCallback: ((Result<Set<Source>, Error>) -> Void)?
    func fetchSources(completionHandler: @escaping (Result<Set<Source>, Error>) -> Void) {
        sourceCallback = completionHandler
    }
"""
runner = r"""
}
@main struct BackgroundFetchCompletionHarness {
    static func main() {
        var passed = 0
        func run(enabled: Bool,
                 sourceResult: Result<Set<Source>, Error>,
                 refreshResult: Result<[String: Result<InstalledApp, Error>], Error>?,
                 throwsOnStart: Bool = false,
                 expected: UIBackgroundFetchResult) {
            let app = AppDelegate()
            var statuses = [UIBackgroundFetchResult]()
            var finished = 0
            UserDefaults.standard.isBackgroundRefreshEnabled = enabled
            AppManager.shared.pending = nil
            AppManager.shared.shouldThrow = throwsOnStart
            app.performBackgroundFetch(
                backgroundFetchCompletionHandler: { statuses.append($0) },
                refreshAppsCompletionHandler: { _ in finished += 1 }
            )
            precondition(statuses.isEmpty && finished == 0,
                         "must wait for sources before reporting completion")
            app.sourceCallback?(sourceResult)
            if enabled && !throwsOnStart {
                precondition(statuses.isEmpty && finished == 0,
                             "must wait for signing/refresh callback")
                guard let refreshResult, let pending = AppManager.shared.pending else {
                    fatalError("expected pending app refresh")
                }
                pending(refreshResult)
            }
            precondition(statuses.count == 1 && statuses[0] == expected && finished == 1,
                         "must complete exactly once after actual refresh")
            passed += 1
        }
        run(enabled: true, sourceResult: .success([]),
            refreshResult: .success(["a": .success(InstalledApp())]), expected: .newData)
        run(enabled: true, sourceResult: .success([]),
            refreshResult: .success(["a": .failure(TestError())]), expected: .failed)
        run(enabled: true, sourceResult: .success([]),
            refreshResult: .success([:]), expected: .noData)
        run(enabled: true, sourceResult: .failure(TestError()),
            refreshResult: .success([:]), expected: .failed)
        run(enabled: true, sourceResult: .success([]),
            refreshResult: nil, throwsOnStart: true, expected: .failed)
        run(enabled: false, sourceResult: .success([]),
            refreshResult: nil, expected: .newData)
        run(enabled: false, sourceResult: .failure(TestError()),
            refreshResult: nil, expected: .failed)
        precondition(passed == 7)
        print("SIDESTORE_BACKGROUND_COMPLETION_7_OF_7_PASS")
    }
}
"""

with tempfile.TemporaryDirectory(prefix="side-background-") as temp:
    program = Path(temp) / "BackgroundFetch.swift"
    program.write_text(stub + method + runner, encoding="utf8")
    binary = Path(temp) / "background-test"
    subprocess.run(["swiftc", "-parse-as-library", str(program), "-o", str(binary)],
                   check=True, timeout=180)
    result = subprocess.run([str(binary)], check=True, timeout=30,
                            text=True, capture_output=True)
    assert "SIDESTORE_BACKGROUND_COMPLETION_7_OF_7_PASS" in result.stdout
    print(result.stdout, end="")
