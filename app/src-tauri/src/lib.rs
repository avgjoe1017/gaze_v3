mod engine;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Initialize engine state
            app.manage(engine::EngineState::new());
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
