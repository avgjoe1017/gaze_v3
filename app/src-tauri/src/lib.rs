mod engine;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Initialize engine state
            app.manage(engine::EngineState::new());
            
            // Webview security is handled by:
            // 1. CSP in tauri.conf.json (navigate-to 'self', frame-ancestors 'none', etc.)
            // 2. CORS and Origin validation in FastAPI backend
            // 3. Token stored only in Rust memory (never in localStorage)
            
            #[cfg(debug_assertions)]
            {
                if let Some(window) = app.get_webview_window("main") {
                    window.open_devtools();
                }
            }
            
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            engine::start_engine,
            engine::stop_engine,
            engine::get_engine_port,
            engine::get_engine_status,
            engine::get_engine_token,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
