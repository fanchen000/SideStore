#!/usr/bin/env python3
"""Compile and execute the REAL AppDelegate background-completion method with stubs.

This is an offline Swift test: no device, signing identity, network or Apple ID.
"""
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
source = (ROOT / "AltStore/AppDelegate.swift").read_text(encoding="utf8")
start = source.index("    func performBackgroundFetch(backgroundFetchCompletionHandler:")
marker = "\n    }\n}\n\nprivate extension AppDelegate"
end = source.index(marker, start) + len("\n    }")
method = source[start:end]

stubs = r'''
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
        get { bool(forKey: "offline.bg.test.enabled") }
        set { set(newValue, forKey: "offline.bg.test.enabled") }
    }
}
enum UIBackgroundFetchResult: String { case failed, newData, noData }
struct TestError: Error {}
final class AppManager {
    static let shared = AppManager()
    var pending: ((Result<[String: Result<InstalledApp, Error>], Error>) -> Void)?
    var failsImmediately = false
    func backgroundRefresh(_ apps: [InstalledApp],
                           completionHandler: @escaping (Result<[String: Result<InstalledApp, Error>], Error>) -> Void
    ) throws -> Int {
        if failsImmediately { throw TestError() }
        pending = completionHandler
        return 1
    }
}
final class AppDelegate {
    var sourceCallback: ((Result<Set<Source>, Error>) -> Void)?
    func fetchSources(completionHandler: @escaping (Result<Set<Source>, Error>) -> Void) {
        sourceCallback = completionHandler
    }
'''
runner = r'''
}
@main struct BackgroundFetchCompletionHarness {
    static func main() {
        var pass = 0
        func run(
            enabled: Bool, sources: Result<Set<Source>, Error>,
            appResult: Result<[String: Result<InstalledApp, Error>], Error>?,
            throwAtStart: Bool = false,
            expected: UIBackgroundFetchResult
        ) {
            let app = AppDelegate()
            var statuses: [UIBackgroundFetchResult] = []
            var finished = 0
            UserDefaults.standard.isBackgroundRefreshEnabled = enabled
            AppManager.shared.pending = nil
            AppManager.shared.failsImmediately = throwAtStart
            app.performBackgroundFetch(
                backgroundFetchCompletionHandler: { statuses.append($0) },
                refreshAppsCompletionHandler: { _ in finished += 1 }
            )
            precondition(statuses.isEmpty && finished == 0,
                         "must not report background completion before source fetch")
            app.sourceCallback?(sources)
            if enabled && !throwAtStart {
                precondition(statuses.isEmpty && finished == 0,
                             "must not report complete while signing refresh is pending")
                guard let appResult, let completion = AppManager.shared.pending else {
                    fatalError("expected an application refresh operation")
                }
                completion(appResult)
            }
            precondition(statuses.count == 1 && statuses[0] == expected && finished == 1,
                         "expected one terminal result, after refresh when enabled")
            pass += 1
        }
        run(enabled: true, sources: .success([]),
            appResult: .success(["a": .success(InstalledApp())]),
            expected: .newData)
        run(enabled: true, sources: .success([]),
            appResult: .success(["a": .failure(TestError())]),
            expected: .failed)
        run(enabled: true, sources: .success([]),
            appResult: .success([:]), expected: .noData)
        run(enabled: true, sources: .failure(TestError()),
            appResult: .success([:]), expected: .failed)
        run(enabled: true, sources: .success([]),
            appResult: nil, throwAtStart: true, expected: .failed)
        run(enabled: false, sources: .success([]),
            appResult: nil, expected: .newData)
        run(enabled: false, sources: .failure(TestError()),
            appResult: nil, expected: .failed)
        print("SIDESTORE_BACKGROUND_COMPLETION_7_OF_7_PASS")
    }
}
'''
with tempfile.TemporaryDirectory(prefix="side-offline-bg-") as temporary:
    path = pathlib.Path(temporary)
    src = path / "main.swift"
    src.write_text(stubs + method + runner, encoding="utf8")
    executable = path / "run-background-test"
    subprocess.run(["swiftc", "-swift-version", "5", "-parse-as-library", str(src), "-o", str(executable)],
                   check=True, timeout=120)
    subprocess.run([str(executable)], check=True, timeout=20)
