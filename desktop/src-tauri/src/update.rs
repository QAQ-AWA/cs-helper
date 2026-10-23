use serde::Serialize;
use std::path::{Path, PathBuf};
use tauri::AppHandle;

fn old_exe_path(current_exe: &Path) -> PathBuf {
    PathBuf::from(format!("{}.old", current_exe.to_string_lossy()))
}

const UPDATE_FAILURE_MARKER: &str = "cs-match-helper-update-failed.marker";

fn update_failure_marker_path() -> PathBuf {
    std::env::temp_dir().join(UPDATE_FAILURE_MARKER)
}

/// 启动时清理残留的旧版本备份或失败标记
pub fn startup_update_maintenance(_app: &AppHandle) {
    if let Ok(current_exe) = std::env::current_exe() {
        let old_exe = old_exe_path(&current_exe);
        if old_exe.is_file() {
            let _ = std::fs::remove_file(old_exe);
        }
    }

    if update_failure_marker_path().is_file() {
        let _ = std::fs::remove_file(update_failure_marker_path());
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateCheckResult {
    pub current_version: String,
    pub has_update: bool,
    pub latest_version: Option<String>,
    pub release_notes: Option<String>,
    pub release_url: Option<String>,
    pub published_at: Option<String>,
    pub download_url: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DownloadUpdateResult {
    pub file_path: String,
    pub sha256: String,
    pub size_bytes: u64,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateProgressEvent {
    pub phase: String,
    pub downloaded_bytes: u64,
    pub total_bytes: Option<u64>,
    pub percent: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ChangelogReleaseSummary {
    pub tag_name: String,
    pub published_at: Option<String>,
    pub html_url: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ChangelogReleaseDetail {
    pub tag_name: String,
    pub published_at: Option<String>,
    pub html_url: String,
    pub body: Option<String>,
}

#[tauri::command]
pub fn get_app_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

/// 检查更新：已彻底停用原作者 CDN 与静默覆盖逻辑，始终保持本地运行独立
#[tauri::command]
pub async fn check_for_update() -> Result<UpdateCheckResult, String> {
    let current_version = get_app_version();
    Ok(UpdateCheckResult {
        current_version,
        has_update: false,
        latest_version: None,
        release_notes: None,
        release_url: Some("https://github.com/QAQ-AWA/cs-helper-exe/releases".to_string()),
        published_at: None,
        download_url: None,
    })
}

#[tauri::command]
pub async fn list_changelog_releases() -> Result<Vec<ChangelogReleaseSummary>, String> {
    Ok(vec![ChangelogReleaseSummary {
        tag_name: "v4.0.0".to_string(),
        published_at: Some("2026-10-22T00:00:00Z".to_string()),
        html_url: "https://github.com/QAQ-AWA/cs-helper-exe/releases/tag/v4.0.0".to_string(),
    }])
}

#[tauri::command]
pub async fn get_changelog_release(_tag: String) -> Result<ChangelogReleaseDetail, String> {
    Ok(ChangelogReleaseDetail {
        tag_name: "v4.0.0".to_string(),
        published_at: Some("2026-10-22T00:00:00Z".to_string()),
        html_url: "https://github.com/QAQ-AWA/cs-helper-exe/releases/tag/v4.0.0".to_string(),
        body: Some(
            "CS 匹配助手 4.0.0：\n\n\
            1. 全面升级 4.0.0 架构与 AI 深度分析 V3；\n\
            2. 独家集成 5E 赛后报告与战绩深度统计面板；\n\
            3. 支持完美世界通行证扫码与 Steam 直接登录；\n\
            4. 彻底移除原作者 CDN 覆盖逻辑与自动更新静默下载，保障代码完全自主可控；\n\
            5. 支持脱机免服务运行与全内嵌打包。"
                .to_string(),
        ),
    })
}

#[tauri::command]
pub async fn download_update(
    _app: AppHandle,
    _version: String,
) -> Result<DownloadUpdateResult, String> {
    Err("已禁用外部自动更新通道，请前往项目 GitHub Releases 手动获取更新。".to_string())
}

#[tauri::command]
pub async fn apply_update_and_restart(
    _app: AppHandle,
    _new_exe_path: String,
) -> Result<(), String> {
    Err("已禁用外部自动更新通道，请前往项目 GitHub Releases 手动获取更新。".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_app_version_format() {
        let version = get_app_version();
        assert!(!version.is_empty());
        assert!(version.contains('.'));
    }

    #[tokio::test]
    async fn test_check_for_update_returns_no_update() {
        let result = check_for_update().await.expect("check_for_update should succeed");
        assert!(!result.has_update);
        assert_eq!(result.current_version, get_app_version());
    }

    #[tokio::test]
    async fn test_changelog_endpoints() {
        let list = list_changelog_releases().await.expect("list releases should succeed");
        assert!(!list.is_empty());
        assert_eq!(list[0].tag_name, "v4.0.0");

        let detail = get_changelog_release("v4.0.0".to_string()).await.expect("get release should succeed");
        assert_eq!(detail.tag_name, "v4.0.0");
        assert!(detail.body.is_some());
    }
}
