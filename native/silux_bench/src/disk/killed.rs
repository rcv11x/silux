//! The file leaves nothing behind when the process dies with it open: no
//! name in the folder and no space taken. Seen by killing a process that is
//! writing it, since no code of ours gets to run then.

use std::io::{BufRead, BufReader};
use std::os::unix::process::ExitStatusExt;
use std::path::Path;
use std::process::{Command, Stdio};
use std::time::Duration;

use crate::common::cancel::Control;
use crate::disk::job::{Direction, Job, Pattern};
use crate::disk::target::testing::Folder;
use crate::disk::target::Target;
use crate::disk::threads;

const FOLDER: &str = "SILUX_BENCH_CHILD_FOLDER";
const DOING: &str = "SILUX_BENCH_CHILD_DOING";
const READY: &str = "silux-bench-child-is-writing";
const BYTES: u64 = 256 << 20;

/// What the killed process runs: this same test binary, asked for this one
/// test. Without the variables it is a test that does nothing.
#[test]
fn the_child_that_writes_until_it_is_killed() {
    let (Some(folder), Some(doing)) = (std::env::var_os(FOLDER), std::env::var_os(DOING)) else {
        return;
    };
    let target = Target::create(Path::new(&folder), BYTES).unwrap();
    let control = Control::default();
    target.fill(1, &control).unwrap();
    println!("{READY}");
    let job = Job {
        pattern: Pattern::Random,
        direction: Direction::Write,
        block: 4096,
        depth: 4,
        seconds: 1.0,
        seed: 1,
    };
    loop {
        if doing == "filling" {
            target.fill(2, &control).unwrap();
        } else {
            threads::run(&target, &job, &control).unwrap();
        }
    }
}

fn killed_while(doing: &str) {
    let folder = Folder::new(&format!("killed-{doing}"));
    // Where no file can be made there is nothing to see.
    if folder.target(BYTES).is_none() {
        return;
    }
    let mut child = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "disk::killed::the_child_that_writes_until_it_is_killed",
            "--nocapture",
        ])
        .env(FOLDER, &folder.0)
        .env(DOING, doing)
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let mut lines = BufReader::new(child.stdout.take().unwrap()).lines();
    assert!(lines.any(|line| line.unwrap().contains(READY)));
    // The file is whole and being written: nothing in the folder even now.
    std::thread::sleep(Duration::from_millis(150));
    assert!(folder.names().is_empty(), "{:?}", folder.names());
    let held = folder.free();

    child.kill().unwrap();
    assert_eq!(child.wait().unwrap().signal(), Some(libc::SIGKILL));
    assert!(folder.names().is_empty(), "{:?}", folder.names());
    // Other programs write to this disk too: half of it back is proof
    // enough that it was freed.
    let back = (0..30).any(|_| {
        std::thread::sleep(Duration::from_millis(100));
        folder.free() >= held + BYTES / 2
    });
    assert!(back, "{held} held, {} now", folder.free());
}

#[test]
fn killed_while_the_file_is_written_nothing_is_left() {
    killed_while("filling");
}

#[test]
fn killed_in_the_middle_of_a_lap_nothing_is_left() {
    killed_while("a-lap");
}
