import Foundation

/// Uploads queued records (PLAN §2.7): multipart `POST /v1/boards` or `POST /v1/allwords` with
/// `Authorization: Bearer <token>`. Form fields: `record` (the JSON, filename record.json) and one
/// `files` part per image (filename = the reference used in the record). The server is idempotent
/// on board_id / record_id, so a retry after a lost response is harmless.
///
/// Outcomes: 2xx or 409 → done (removed); 401/403 → stop until the config is fixed; 404/405 →
/// retry (server not updated yet); other 4xx →
/// the record is malformed for this server, moved to `failed/`; 5xx or network error →
/// exponential backoff (1 s doubling to 5 min, ±20% jitter) and retry.
public final class Uploader {
    public enum Outcome: Equatable, Sendable {
        case uploaded(String)
        case empty
        case retry(after: TimeInterval)
        case unauthorized
        case rejected(String, Int)
    }

    public let baseURL: URL
    public let token: String
    public let queue: RecordQueue
    let session: URLSession
    let jitter: () -> Double
    public private(set) var failures = 0

    public init(baseURL: URL, token: String, queue: RecordQueue, session: URLSession = .shared,
                jitter: @escaping () -> Double = { Double.random(in: 0.8...1.2) }) {
        self.baseURL = baseURL
        self.token = token
        self.queue = queue
        self.session = session
        self.jitter = jitter
    }

    public func backoff() -> TimeInterval {
        min(300, pow(2, Double(max(0, failures - 1)))) * jitter()
    }

    static func request(for item: RecordQueue.Item, baseURL: URL, token: String) throws -> URLRequest {
        let path = item.kind == "board" ? "v1/boards" : "v1/allwords"
        var req = URLRequest(url: baseURL.appendingPathComponent(path), timeoutInterval: 30)
        req.httpMethod = "POST"
        let boundary = "wh-\(UUID().uuidString)"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        if !token.isEmpty { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        req.setValue(item.id, forHTTPHeaderField: "Idempotency-Key")
        var body = Data()
        func part(name: String, filename: String, type: String, data: Data) {
            body.append(Data("--\(boundary)\r\n".utf8))
            body.append(Data("Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n".utf8))
            body.append(Data("Content-Type: \(type)\r\n\r\n".utf8))
            body.append(data)
            body.append(Data("\r\n".utf8))
        }
        part(name: "record", filename: "record.json", type: "application/json", data: try Data(contentsOf: item.recordURL))
        for img in item.images() {
            part(name: "files", filename: img.lastPathComponent, type: "image/jpeg", data: try Data(contentsOf: img))
        }
        body.append(Data("--\(boundary)--\r\n".utf8))
        req.httpBody = body
        return req
    }

    /// Try the oldest queued record once.
    public func uploadNext() async -> Outcome {
        guard let item = queue.pending().first else { return .empty }
        do {
            let req = try Self.request(for: item, baseURL: baseURL, token: token)
            let (_, resp) = try await session.data(for: req)
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            switch code {
            case 200..<300, 409:
                queue.remove(item)
                failures = 0
                return .uploaded(item.id)
            case 401, 403:
                return .unauthorized
            case 404, 405:  // endpoint missing: the server is older than the app — keep and retry
                failures += 1
                return .retry(after: backoff())
            case 400..<500:
                queue.markFailed(item)
                return .rejected(item.id, code)
            default:
                failures += 1
                return .retry(after: backoff())
            }
        } catch {
            failures += 1
            return .retry(after: backoff())
        }
    }

    /// Upload until the queue is empty, waiting between retries; stops on `.unauthorized`.
    /// `sleep` is injectable for tests.
    public func drain(maxAttempts: Int = 1000,
                      sleep: (TimeInterval) async -> Void = { try? await Task.sleep(nanoseconds: UInt64($0 * 1e9)) }) async -> Outcome {
        var last = Outcome.empty
        for _ in 0..<maxAttempts {
            last = await uploadNext()
            switch last {
            case .empty, .unauthorized: return last
            case .retry(let after): await sleep(after)
            case .uploaded, .rejected: continue
            }
        }
        return last
    }
}
