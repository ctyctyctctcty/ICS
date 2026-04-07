# VPN Automation README

## 概要
このツールは、Excel の一覧をもとに VPN 用のユーザー設定を自動で登録・更新するためのスクリプトです。

主な処理は以下です。
- ユーザーロールの作成または更新
- ユーザーロールのマッピング設定
- ACL（アクセス制御）の作成または更新

## 前提
- 実行場所: `C:\vpn-automation`
- Python 3.x が利用できること
- `config/settings.json` と `config/.env` が設定済みであること
- ICS に接続できること

## 入力ファイル
入力ファイルは `input.xlsx` を使用します。

想定カラム:
- `userID`
- `name`
- `company`
- `email`
- `hostname`
- `IP`

`IP` には以下のどちらかを設定します。
- 固定IP（例: `10.10.10.10`）
- `Internet Access`

## 実行方法
プロジェクトのルートで以下を実行します。

```powershell
cd C:\vpn-automation
python -m src.main
```

## 実行結果
処理結果はログに出力されます。
ログは `data/logs` 配下に保存されます。

例:
- Role created / Role updated / Role already exists
- Role mapping inserted / updated / skip
- ACL created / updated / skip

## 補足
- 既存ユーザーに対して再実行した場合は、差分がある設定のみ更新されます。
- `Internet Access` の場合は共有 ACL を更新します。
- 固定IP の場合はユーザー用 ACL を作成または更新します。

## よく使う確認ポイント
- `config/settings.json` の接続先設定
- `config/.env` の認証情報
- `input.xlsx` の列名・値
- 実行後の `data/logs` の内容

## 注意
- 実行前に `input.xlsx` の内容を確認してください。
- 既存設定に対して更新が入るため、テストデータで事前確認することをおすすめします。
