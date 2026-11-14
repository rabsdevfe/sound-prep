use std::path::{Path, PathBuf};
use std::{env, fs, io};

fn main() {
    prepare_dev_sidecar();
    tauri_build::build()
}

/// Lets `tauri dev` run the frozen core sidecar (ADR 0001).
///
/// Inside a `.app` the PyInstaller launcher finds its code through the bundle mapping
/// (`binaries/fw` -> `Contents/Frameworks`, `binaries/res` -> `Contents/Resources/pyi`). Tauri
/// only copies the launcher next to the dev binary, where it would look for `_internal/` and die.
/// For debug builds, rebuild the same layout beside the launcher: `Frameworks/`,
/// `Resources/pyi/` and `_internal -> Frameworks`. Running from `build.rs` ties it to the cargo
/// target directory, so it is recreated after `cargo clean`. Release bundles are untouched.
fn prepare_dev_sidecar() {
    println!("cargo:rerun-if-changed=binaries");
    if env::var("PROFILE").as_deref() != Ok("debug") {
        return;
    }
    // OUT_DIR is <target>/<profile>/build/<package>/<hash>/out: the profile directory is the
    // parent of the `build` ancestor.
    let out = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR"));
    let Some(profile_dir) = out
        .ancestors()
        .find(|dir| dir.file_name().is_some_and(|name| name == "build"))
        .and_then(Path::parent)
    else {
        return;
    };
    // A cache may restore build state but prune these outputs; a missing path forces a rerun.
    for generated in ["Frameworks", "Resources/pyi", "_internal"] {
        println!(
            "cargo:rerun-if-changed={}",
            profile_dir.join(generated).display()
        );
    }
    let manifest = PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR"));
    let (fw, res) = (manifest.join("binaries/fw"), manifest.join("binaries/res"));
    if !fw.is_dir() || !res.is_dir() {
        return; // not built yet; tauri_build reports the missing launcher itself
    }
    if let Err(error) = assemble(profile_dir, &fw, &res) {
        println!("cargo:warning=could not prepare the dev sidecar layout: {error}");
    }
}

#[cfg(unix)]
fn assemble(profile_dir: &Path, fw: &Path, res: &Path) -> io::Result<()> {
    let frameworks = profile_dir.join("Frameworks");
    let pyi = profile_dir.join("Resources").join("pyi");
    let internal = profile_dir.join("_internal");
    for path in [&frameworks, &pyi, &internal] {
        match fs::symlink_metadata(path) {
            Ok(meta) if meta.is_dir() => fs::remove_dir_all(path)?,
            Ok(_) => fs::remove_file(path)?,
            Err(_) => {}
        }
    }
    fs::create_dir_all(pyi.parent().expect("Resources directory"))?;
    copy_tree(fw, &frameworks)?;
    copy_tree(res, &pyi)?;
    std::os::unix::fs::symlink("Frameworks", &internal)
}

#[cfg(not(unix))]
fn assemble(_profile_dir: &Path, _fw: &Path, _res: &Path) -> io::Result<()> {
    Ok(())
}

/// Copies a tree keeping symlinks as symlinks (the layout relies on relative ones).
#[cfg(unix)]
fn copy_tree(from: &Path, to: &Path) -> io::Result<()> {
    fs::create_dir_all(to)?;
    for entry in fs::read_dir(from)? {
        let entry = entry?;
        let (source, target) = (entry.path(), to.join(entry.file_name()));
        let kind = entry.file_type()?;
        if kind.is_symlink() {
            std::os::unix::fs::symlink(fs::read_link(&source)?, &target)?;
        } else if kind.is_dir() {
            copy_tree(&source, &target)?;
        } else {
            fs::copy(&source, &target)?;
        }
    }
    Ok(())
}
