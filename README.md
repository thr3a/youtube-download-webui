youtubeなどの動画URLを入れるとyt-dlpがダウンロードしてくれるサイトを作りたい
サーバーはuv run uvicorn app.main:app --reload --host 0.0.0.0 --port 3000で開発中は起動する
HTMLのフロントエンドとDB登録のAPIまで実装した。
実際の動画ダウンロード部分をfastapiのBackgroundTasksを使用して実装してください。

要件

# UI

- URLを入れる1行インプット
- 保存形式 動画/音声のみか
- 開始ボタン
- 履歴 動画一覧
 - 入力された動画はここに入る
  - ステータス、動画タイトル、ファイルサイズ、ボタン
  - ステータスはキューに溜まっている未実行、ダウンロード済み、エラー、キャンセル済み
  - ボタンはダウンロード済みの場合は保存、エラーまたはキャンセル済みの場合は再試行
  - ダウンロード中の動画は進捗率をプログレスバーで出す
  - エラー内容もUIに表示できるならしたい

# 仕様

- プライベートで一人しか使わない想定
- 動画の履歴管理はsqliteで行う(直下にwebui.db作成)
- 動画のダウンロードは1並列
- プレイリストが入れられた場合、yt-dlpでは複数動画としてダウンロードできるが一旦実装しない　エラーとして処理して良い
- タイムゾーンはasia/tokyoのみで動く前提で良い
- 動画は./downloads/に保存される
- ダウンロードしようとした場合にすでにファイルがある場合はスキップ
- プログラムは uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 3000 で起動する
- HTMLでfastapi上に実装する /でアクセス
  
# DBスキーマ

```sql
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT,
    -- ステータス：キュー登録(queued), ダウンロード中(downloading), 完了(completed), エラー(error), キャンセル(canceled)
    status TEXT NOT NULL CHECK(status IN ('queued', 'downloading', 'completed', 'error', 'canceled')) DEFAULT 'queued',
    -- 保存形式：動画(video), 音声(audio)
    download_type TEXT NOT NULL CHECK(download_type IN ('video', 'audio')),
    file_size INTEGER NOT NULL DEFAULT 0,
    progress INTEGER NOT NULL DEFAULT 0,
    file_path TEXT,
    error_message TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

# まだついかしなくていい機能

- アプリケーション再起動時の挙動
  - もし動画のダウンロード中にアプリケーションを停止・再起動したらstatus が downloading のまま止まってしまう
  - 不整合を防ぐために起動時に status が downloading のレコードを探して、それを error に更新する
