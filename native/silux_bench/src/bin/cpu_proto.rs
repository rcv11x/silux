//! A development tool for the renderer prototype: it renders, compares the
//! kernels bit by bit, times a run and writes a picture to look at. It is
//! not part of the Python module and nothing ships it.
//!
//! ```text
//! cpu_proto info   [--detail D]
//! cpu_proto check  [--detail D] [--passes P] [--threads N|all]
//! cpu_proto render --png FILE [--table FILE] [--kernel K] [--detail D] [--passes P] [--threads N|all]
//! cpu_proto timed  --seconds S [--warmup S] [--kernel K] [--detail D] [--passes P]
//!                  [--threads N|all | --cpus 0,1,… | --loose N]
//!                  [--report-hz HZ --report-to FILE] [--rows FILE] [--label TEXT]
//! cpu_proto tiles  --csv FILE [--cpu C] [--kernel K] [--detail D] [--passes P] [--repeat R]
//! ```

use std::collections::HashMap;
use std::fmt::Write as _;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::Path;
use std::process::ExitCode;
use std::str::FromStr;
use std::sync::Mutex;

use silux_bench::common::cancel::Control;
use silux_bench::common::hash::Fingerprint;
use silux_bench::common::timer::now_ns;
use silux_bench::common::topology::allowed_cpus;
use silux_bench::cpu::render::film::{pass_samples, to_screen, Layout};
use silux_bench::cpu::render::scene::{prototype, Scene};
use silux_bench::cpu::render::Kernel;
use silux_bench::cpu::workers::{run, Outcome, Plan, Reporter, Row, Stop};

type Fail = Box<dyn std::error::Error>;

fn main() -> ExitCode {
    match start() {
        Ok(code) => code,
        Err(why) => {
            eprintln!("cpu_proto: {why}");
            ExitCode::from(2)
        }
    }
}

fn start() -> Result<ExitCode, Fail> {
    let mut args = std::env::args().skip(1);
    let command = args
        .next()
        .ok_or("which command? See the top of cpu_proto.rs")?;
    let options = Options::parse(args)?;
    match command.as_str() {
        "info" => info(&options),
        "check" => check(&options),
        "render" => render(&options),
        "timed" => timed(&options),
        "tiles" => tiles(&options),
        other => Err(format!("no command called {other}").into()),
    }
}

struct Options(HashMap<String, String>);

impl Options {
    /// `--key value` pairs, and nothing else.
    fn parse(mut args: impl Iterator<Item = String>) -> Result<Options, Fail> {
        let mut options = HashMap::new();
        while let Some(key) = args.next() {
            let name = key
                .strip_prefix("--")
                .ok_or_else(|| format!("expected an option, got {key}"))?;
            let value = args.next().ok_or_else(|| format!("{key} needs a value"))?;
            options.insert(name.to_owned(), value);
        }
        Ok(Options(options))
    }

    /// A mistyped option would measure something else without saying so.
    fn only(&self, known: &[&str]) -> Result<(), Fail> {
        match self.0.keys().find(|key| !known.contains(&key.as_str())) {
            Some(unknown) => Err(format!("this command has no --{unknown}").into()),
            None => Ok(()),
        }
    }

    fn text(&self, key: &str) -> Option<&str> {
        self.0.get(key).map(String::as_str)
    }

    fn need(&self, key: &str) -> Result<&str, Fail> {
        self.text(key)
            .ok_or_else(|| format!("--{key} is needed").into())
    }

    fn number<T: FromStr>(&self, key: &str, default: T) -> Result<T, Fail> {
        match self.text(key) {
            Some(text) => text
                .parse()
                .map_err(|_| format!("--{key} {text} isn't a number").into()),
            None => Ok(default),
        }
    }

    fn kernel(&self) -> Result<Kernel, Fail> {
        let kernel = match self.text("kernel") {
            Some(key) => Kernel::from_key(key).ok_or_else(|| format!("no kernel called {key}"))?,
            None => Kernel::widest(),
        };
        if !kernel.is_available() {
            return Err(format!("this processor doesn't run {}", kernel.key()).into());
        }
        Ok(kernel)
    }

    fn scene(&self) -> Result<(Scene, u32, f64), Fail> {
        let detail = self.number("detail", 2)?;
        let begin = now_ns();
        let scene = prototype(detail)?;
        Ok((scene, detail, seconds(now_ns() - begin)))
    }

    /// The CPUs to run on: `--cpus` by number, `--loose` unpinned, or
    /// `--threads`, one each on the first CPUs this process may use.
    fn cpus(&self) -> Result<Vec<Option<usize>>, Fail> {
        let allowed = allowed_cpus();
        if let Some(list) = self.text("cpus") {
            return list
                .split(',')
                .map(|cpu| {
                    let cpu: usize = cpu.parse().map_err(|_| format!("--cpus {list}"))?;
                    if !allowed.contains(&cpu) {
                        return Err(format!("this process may not run on CPU {cpu}").into());
                    }
                    Ok(Some(cpu))
                })
                .collect();
        }
        if self.text("loose").is_some() {
            return Ok(vec![None; self.number("loose", 1usize)?.max(1)]);
        }
        let threads = match self.text("threads") {
            None | Some("all") => allowed.len(),
            Some(_) => self.number("threads", 1usize)?.clamp(1, allowed.len()),
        };
        Ok(allowed.into_iter().take(threads).map(Some).collect())
    }
}

fn seconds(ns: u64) -> f64 {
    ns as f64 / 1e9
}

fn megabytes(bytes: usize) -> f64 {
    bytes as f64 / (1024.0 * 1024.0)
}

fn describe(scene: &Scene, detail: u32, built: f64) -> String {
    let bvh = &scene.bvh;
    let children: usize = bvh
        .nodes
        .iter()
        .map(|node| node.child.iter().filter(|c| **c != u32::MAX).count())
        .sum();
    format!(
        "scene: detail {detail}, {} triangles, {} nodes ({:.2} children each), {} leaves \
         ({:.2} triangles each), depth {}, {:.1} MB, built in {built:.2} s",
        scene.triangles(),
        bvh.nodes.len(),
        children as f64 / bvh.nodes.len().max(1) as f64,
        bvh.leaves.len(),
        scene.triangles() as f64 / bvh.leaves.len().max(1) as f64,
        bvh.depth,
        megabytes(scene.bytes()),
    )
}

fn info(options: &Options) -> Result<ExitCode, Fail> {
    options.only(&["detail"])?;
    let kernels: Vec<&str> = Kernel::ALL
        .into_iter()
        .filter(|kernel| kernel.is_available())
        .map(Kernel::key)
        .collect();
    println!(
        "kernels here: {}; widest exact: {}",
        kernels.join(", "),
        Kernel::widest().key()
    );
    println!("cpus allowed: {}", allowed_cpus().len());
    let (scene, detail, built) = options.scene()?;
    println!("{}", describe(&scene, detail, built));
    Ok(ExitCode::SUCCESS)
}

fn whole_table(passes: u32) -> Stop {
    Stop::AfterUnits(u64::from(passes) * u64::from(Layout::FULL.tiles()))
}

fn plan<'a>(scene: &'a Scene, kernel: Kernel, cpus: Vec<Option<usize>>, passes: u32) -> Plan<'a> {
    Plan {
        scene,
        layout: Layout::FULL,
        kernel,
        cpus,
        passes,
        stop: whole_table(passes),
        warmup_ns: 0,
        keep_film: false,
        reporter: None,
    }
}

/// The same table with every kernel and with one thread and many: all of
/// them have to give the same bits. Exit code 1 if any doesn't.
fn check(options: &Options) -> Result<ExitCode, Fail> {
    options.only(&["detail", "passes", "threads"])?;
    let passes = options.number("passes", 4)?;
    let cpus = options.cpus()?;
    let (scene, detail, built) = options.scene()?;
    println!("{}", describe(&scene, detail, built));
    let control = Control::default();
    let mut reference: Option<(String, Outcome)> = None;
    let mut agree = true;
    let mut runs = Vec::new();
    for kernel in Kernel::EXACT {
        if kernel.is_available() {
            runs.push((kernel, cpus.clone()));
        }
    }
    // The widest again on one thread: the split between threads mustn't show.
    if cpus.len() > 1 {
        runs.push((Kernel::widest(), cpus.iter().take(1).copied().collect()));
    }
    for (kernel, cpus) in runs {
        let name = format!("{} x{}", kernel.key(), cpus.len());
        let outcome = run(&plan(&scene, kernel, cpus, passes), &control)?;
        let work = outcome.counters();
        println!(
            "{name:>14}: table {:016x}  {} units, {} paths, {} rays, weight {}, strays {}, {:.2} s",
            outcome.table_id(),
            outcome.rows.len(),
            work.paths,
            work.rays,
            work.weight(),
            work.strays,
            seconds(outcome.wall_ns),
        );
        match &reference {
            None => reference = Some((name, outcome)),
            Some((first, expected)) => {
                let differ = differing(&expected.rows, &outcome.rows);
                if differ > 0 || expected.rows.len() != outcome.rows.len() {
                    agree = false;
                    println!("    DIFFERENT from {first} in {differ} units");
                }
            }
        }
    }
    if Kernel::Avx2Fused.is_available() {
        if let Some((_, expected)) = &reference {
            let fused = run(&plan(&scene, Kernel::Avx2Fused, cpus, passes), &control)?;
            println!(
                "    avx2-fused: table {:016x}  another class: {} of {} units differ",
                fused.table_id(),
                differing(&expected.rows, &fused.rows),
                fused.rows.len(),
            );
        }
    }
    println!(
        "{}",
        if agree {
            "SAME BITS"
        } else {
            "NOT THE SAME BITS"
        }
    );
    Ok(if agree {
        ExitCode::SUCCESS
    } else {
        ExitCode::from(1)
    })
}

fn differing(expected: &[Row], got: &[Row]) -> usize {
    expected
        .iter()
        .zip(got)
        .filter(|(a, b)| (a.fingerprint, a.counters) != (b.fingerprint, b.counters))
        .count()
}

fn render(options: &Options) -> Result<ExitCode, Fail> {
    options.only(&[
        "png", "table", "kernel", "detail", "passes", "threads", "cpus",
    ])?;
    let png = options.need("png")?;
    let passes: u32 = options.number("passes", 6)?;
    let kernel = options.kernel()?;
    let (scene, detail, built) = options.scene()?;
    println!("{}", describe(&scene, detail, built));
    let mut plan = plan(&scene, kernel, options.cpus()?, passes);
    plan.keep_film = true;
    let outcome = run(&plan, &Control::default())?;
    let work = outcome.counters();
    println!(
        "{}: table {:016x}, {} paths, {} rays in {:.2} s",
        kernel.key(),
        outcome.table_id(),
        work.paths,
        work.rays,
        seconds(outcome.wall_ns),
    );
    let film = outcome.film.as_deref().ok_or("no film")?;
    let (_, last) = pass_samples(passes.saturating_sub(1));
    let samples = if passes <= 1 { 1 } else { last * 2 };
    let pixels: Vec<u8> = film.iter().map(|sum| to_screen(*sum, samples)).collect();
    write_png(
        Path::new(png),
        Layout::FULL.width,
        Layout::FULL.height,
        &pixels,
    )?;
    println!("{png}: {samples} samples per pixel");
    if let Some(table) = options.text("table") {
        write_rows(Path::new(table), &outcome.rows)?;
    }
    Ok(ExitCode::SUCCESS)
}

fn write_rows(path: &Path, rows: &[Row]) -> Result<(), Fail> {
    let mut out = BufWriter::new(File::create(path)?);
    writeln!(
        out,
        "pass,tile,fingerprint,nodes,leaves,rays,paths,begin_ns,end_ns,worker,counted"
    )?;
    for row in rows {
        writeln!(
            out,
            "{},{},{:016x},{},{},{},{},{},{},{},{}",
            row.unit.pass,
            row.unit.tile,
            row.fingerprint,
            row.counters.nodes,
            row.counters.leaves,
            row.counters.rays,
            row.counters.paths,
            row.begin_ns,
            row.end_ns,
            row.worker,
            u8::from(row.counted),
        )?;
    }
    Ok(out.flush()?)
}

/// What the machine was doing around a measurement.
struct Conditions {
    governor: String,
    driver: String,
    preference: String,
    boost: String,
    huge_pages: String,
    load: String,
    millidegrees: Option<i64>,
    /// Busy and total jiffies of the whole machine, and this process's own.
    jiffies: Option<(u64, u64, u64)>,
}

fn read(path: &str) -> String {
    std::fs::read_to_string(path)
        .map(|text| text.trim().to_owned())
        .unwrap_or_else(|_| "?".to_owned())
}

/// The processor's own temperature sensor, whichever driver it comes from.
fn temperature() -> Option<i64> {
    for entry in std::fs::read_dir("/sys/class/hwmon").ok()?.flatten() {
        let path = entry.path();
        let name = std::fs::read_to_string(path.join("name")).unwrap_or_default();
        if ["k10temp", "zenpower", "coretemp"].contains(&name.trim()) {
            let text = std::fs::read_to_string(path.join("temp1_input")).ok()?;
            return text.trim().parse().ok();
        }
    }
    None
}

fn jiffies() -> Option<(u64, u64, u64)> {
    let stat = std::fs::read_to_string("/proc/stat").ok()?;
    let fields: Vec<u64> = stat
        .lines()
        .next()?
        .split_whitespace()
        .skip(1)
        .filter_map(|field| field.parse().ok())
        .collect();
    // user nice system idle iowait irq softirq steal
    let [user, nice, system, idle, iowait, irq, softirq, steal] = *fields.get(..8)? else {
        return None;
    };
    let busy = user + nice + system + irq + softirq + steal;
    let own = std::fs::read_to_string("/proc/self/stat").ok()?;
    // After the name, which may hold spaces: state is field 3, utime 14.
    let after = own.rsplit_once(')')?.1;
    let mut fields = after.split_whitespace().skip(11);
    let utime: u64 = fields.next()?.parse().ok()?;
    let stime: u64 = fields.next()?.parse().ok()?;
    Some((busy, busy + idle + iowait, utime + stime))
}

impl Conditions {
    fn now() -> Conditions {
        let cpu0 = "/sys/devices/system/cpu/cpu0/cpufreq";
        let boost = [
            "/sys/devices/system/cpu/cpufreq/boost",
            "/sys/devices/system/cpu/intel_pstate/no_turbo",
        ]
        .into_iter()
        .map(|path| (path, read(path)))
        .find(|(_, value)| value != "?")
        .map_or_else(
            || "?".to_owned(),
            |(path, value)| format!("{}={value}", path.rsplit('/').next().unwrap_or(path)),
        );
        Conditions {
            governor: read(&format!("{cpu0}/scaling_governor")),
            driver: read(&format!("{cpu0}/scaling_driver")),
            preference: read(&format!("{cpu0}/energy_performance_preference")),
            boost,
            huge_pages: read("/sys/kernel/mm/transparent_hugepage/enabled"),
            load: read("/proc/loadavg")
                .split_whitespace()
                .next()
                .unwrap_or("?")
                .to_owned(),
            millidegrees: temperature(),
            jiffies: jiffies(),
        }
    }

    /// The share of the machine others took between `self` and `after`, in
    /// percent of all its CPUs.
    fn background(&self, after: &Conditions) -> Option<f64> {
        let (busy0, total0, own0) = self.jiffies?;
        let (busy1, total1, own1) = after.jiffies?;
        let total = total1.checked_sub(total0)? as f64;
        let others = (busy1.checked_sub(busy0)? as f64) - (own1.checked_sub(own0)? as f64);
        (total > 0.0).then(|| (others / total * 100.0).max(0.0))
    }
}

fn degrees(millidegrees: Option<i64>) -> String {
    millidegrees.map_or_else(
        || "null".to_owned(),
        |m| format!("{:.1}", m as f64 / 1000.0),
    )
}

/// The work per second of each ten seconds of the counted stretch.
fn curve(outcome: &Outcome, warmup_ns: u64, ns: u64) -> Vec<f64> {
    const WINDOW: u64 = 10_000_000_000;
    let mut windows = vec![0u64; (ns / WINDOW) as usize];
    for row in outcome.rows.iter().filter(|row| row.counted) {
        let at = (row.end_ns.saturating_sub(warmup_ns) / WINDOW) as usize;
        if let Some(window) = windows.get_mut(at) {
            *window += row.counters.weight();
        }
    }
    windows
        .into_iter()
        .map(|weight| weight as f64 / 10.0)
        .collect()
}

/// A run as the benchmark would do it: for a time, counting work. One line
/// of JSON with the figure and the conditions it was taken in.
fn timed(options: &Options) -> Result<ExitCode, Fail> {
    options.only(&[
        "seconds",
        "warmup",
        "kernel",
        "detail",
        "passes",
        "threads",
        "cpus",
        "loose",
        "report-hz",
        "report-to",
        "rows",
        "label",
    ])?;
    let run_seconds: f64 = options.number("seconds", 10.0)?;
    let warmup: f64 = options.number("warmup", 2.0)?;
    let passes: u32 = options.number("passes", 13)?;
    let kernel = options.kernel()?;
    let cpus = options.cpus()?;
    let (scene, detail, _) = options.scene()?;
    let reporter = match options.text("report-hz") {
        Some(_) => Some(Reporter {
            hz: options.number("report-hz", 15.0)?,
            sink: Mutex::new(Box::new(File::create(options.need("report-to")?)?)),
        }),
        None => None,
    };
    let reported = reporter.as_ref().map_or(0.0, |reporter| reporter.hz);
    let mut plan = plan(&scene, kernel, cpus, passes);
    plan.stop = Stop::AfterNs((run_seconds * 1e9) as u64);
    plan.warmup_ns = (warmup * 1e9) as u64;
    plan.reporter = reporter;

    let before = Conditions::now();
    let outcome = run(&plan, &Control::default())?;
    let after = Conditions::now();

    let work = outcome.counters();
    let rate = outcome.rate();
    let per_weight = |count: u64| rate * count as f64 / work.weight().max(1) as f64;
    let hz: Vec<f64> = outcome
        .workers
        .iter()
        .filter_map(|worker| worker.hz)
        .collect();
    let ghz = |pick: fn(f64, f64) -> f64, start: f64| {
        if hz.is_empty() {
            "null".to_owned()
        } else {
            format!("{:.3}", hz.iter().copied().fold(start, pick) / 1e9)
        }
    };
    let mean_ghz = if hz.is_empty() {
        "null".to_owned()
    } else {
        format!("{:.3}", hz.iter().sum::<f64>() / hz.len() as f64 / 1e9)
    };
    let cpus: Vec<String> = outcome
        .workers
        .iter()
        .map(|worker| {
            worker
                .cpu
                .map_or_else(|| "null".to_owned(), |cpu| cpu.to_string())
        })
        .collect();
    let rates: Vec<String> = outcome
        .workers
        .iter()
        .map(|worker| format!("{:.0}", worker.rate()))
        .collect();
    let curve: Vec<String> = curve(&outcome, plan.warmup_ns, (run_seconds * 1e9) as u64)
        .into_iter()
        .map(|rate| format!("{rate:.0}"))
        .collect();
    let mut line = String::new();
    write!(
        line,
        "{{\"label\":\"{}\",\"kernel\":\"{}\",\"detail\":{detail},\"passes\":{passes},\
         \"threads\":{},\"cpus\":[{}],\"seconds\":{run_seconds},\"warmup\":{warmup},\
         \"report_hz\":{reported},\"rate\":{rate:.0},\"rays_per_s\":{:.0},\"paths_per_s\":{:.0},\
         \"units\":{},\"strays\":{},\"scene_mb\":{:.1},\"wall_s\":{:.3},",
        options.text("label").unwrap_or(""),
        kernel.key(),
        outcome.workers.len(),
        cpus.join(","),
        per_weight(work.rays),
        per_weight(work.paths),
        outcome
            .workers
            .iter()
            .map(|worker| worker.units)
            .sum::<u64>(),
        work.strays,
        megabytes(scene.bytes()),
        seconds(outcome.wall_ns),
    )?;
    write!(
        line,
        "\"ghz_min\":{},\"ghz_mean\":{mean_ghz},\"ghz_max\":{},\"governor\":\"{}\",\
         \"driver\":\"{}\",\"epp\":\"{}\",\"boost\":\"{}\",\"thp\":\"{}\",\"load_before\":\"{}\",\
         \"background_pct\":{},\"temp_before\":{},\"temp_after\":{},\"thread_rates\":[{}],\
         \"curve\":[{}]}}",
        ghz(f64::min, f64::INFINITY),
        ghz(f64::max, 0.0),
        before.governor,
        before.driver,
        before.preference,
        before.boost,
        before.huge_pages,
        before.load,
        before
            .background(&after)
            .map_or_else(|| "null".to_owned(), |pct| format!("{pct:.2}")),
        degrees(before.millidegrees),
        degrees(after.millidegrees),
        rates.join(","),
        curve.join(","),
    )?;
    println!("{line}");
    if let Some(rows) = options.text("rows") {
        write_rows(Path::new(rows), &outcome.rows)?;
    }
    Ok(ExitCode::SUCCESS)
}

/// Every unit of the table on one pinned thread, timed: what its work has
/// to be proportional to. With `--repeat`, the shortest time of each unit,
/// which is the one nothing else got into.
fn tiles(options: &Options) -> Result<ExitCode, Fail> {
    options.only(&["csv", "cpu", "kernel", "detail", "passes", "repeat"])?;
    let csv = options.need("csv")?;
    let passes: u32 = options.number("passes", 4)?;
    let repeat: u32 = options.number("repeat", 3)?;
    let kernel = options.kernel()?;
    let cpu = options.number("cpu", allowed_cpus().first().copied().unwrap_or(0))?;
    let (scene, detail, built) = options.scene()?;
    eprintln!("{}", describe(&scene, detail, built));
    let control = Control::default();
    let mut best: Vec<Row> = Vec::new();
    let mut tables = Fingerprint::default();
    for round in 0..repeat.max(1) {
        let outcome = run(&plan(&scene, kernel, vec![Some(cpu)], passes), &control)?;
        tables.word(outcome.table_id());
        eprintln!(
            "round {round}: table {:016x}, {:.2} s",
            outcome.table_id(),
            seconds(outcome.wall_ns)
        );
        if best.is_empty() {
            best = outcome.rows;
            continue;
        }
        for (kept, row) in best.iter_mut().zip(&outcome.rows) {
            if (row.fingerprint, row.counters) != (kept.fingerprint, kept.counters) {
                return Err("a unit came out different in another round".into());
            }
            if row.end_ns - row.begin_ns < kept.end_ns - kept.begin_ns {
                *kept = *row;
            }
        }
    }
    write_rows(Path::new(csv), &best)?;
    Ok(ExitCode::SUCCESS)
}

/// A PNG without compression: enough to look at a picture, and no
/// dependency to write it.
fn write_png(path: &Path, width: u32, height: u32, rgb: &[u8]) -> Result<(), Fail> {
    let row = width as usize * 3;
    if row == 0 || rgb.len() != row * height as usize {
        return Err("the picture isn't the size it says".into());
    }
    let mut raw = Vec::with_capacity(rgb.len() + height as usize);
    for line in rgb.chunks_exact(row) {
        raw.push(0);
        raw.extend_from_slice(line);
    }
    // A zlib stream of stored blocks, each at most 65 535 bytes.
    let mut data = vec![0x78, 0x01];
    let blocks = raw.chunks(65_535);
    let last = blocks.len().saturating_sub(1);
    for (index, block) in blocks.enumerate() {
        let length = block.len() as u16;
        data.push(u8::from(index == last));
        data.extend_from_slice(&length.to_le_bytes());
        data.extend_from_slice(&(!length).to_le_bytes());
        data.extend_from_slice(block);
    }
    let (mut a, mut b) = (1u32, 0u32);
    for byte in &raw {
        a = (a + u32::from(*byte)) % 65_521;
        b = (b + a) % 65_521;
    }
    data.extend_from_slice(&(b << 16 | a).to_be_bytes());

    let mut header = Vec::new();
    header.extend_from_slice(&width.to_be_bytes());
    header.extend_from_slice(&height.to_be_bytes());
    // Eight bits a channel, RGB, and the only compression, filter and
    // interlace methods there are.
    header.extend_from_slice(&[8, 2, 0, 0, 0]);

    let mut out = BufWriter::new(File::create(path)?);
    out.write_all(b"\x89PNG\r\n\x1a\n")?;
    for (kind, body) in [(b"IHDR", &header), (b"IDAT", &data), (b"IEND", &Vec::new())] {
        out.write_all(&(body.len() as u32).to_be_bytes())?;
        out.write_all(kind)?;
        out.write_all(body)?;
        out.write_all(&crc32(kind.iter().chain(body)).to_be_bytes())?;
    }
    Ok(out.flush()?)
}

fn crc32<'a>(bytes: impl Iterator<Item = &'a u8>) -> u32 {
    let mut crc = u32::MAX;
    for byte in bytes {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            crc = if crc & 1 == 1 {
                (crc >> 1) ^ 0xEDB8_8320
            } else {
                crc >> 1
            };
        }
    }
    !crc
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_checksum_is_the_standard_one() {
        // The check value every CRC-32 implementation documents.
        assert_eq!(crc32(b"123456789".iter()), 0xCBF4_3926);
        assert_eq!(crc32(b"IEND".iter()), 0xAE42_6082);
    }

    #[test]
    fn a_picture_is_written_as_a_png_any_reader_takes() {
        let path = std::env::temp_dir().join(format!("silux-cpu-proto-{}.png", std::process::id()));
        // Three pixels by two: red, green, blue over white, grey, black.
        let rgb = [
            255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255, 128, 128, 128, 0, 0, 0,
        ];
        write_png(&path, 3, 2, &rgb).unwrap();
        let bytes = std::fs::read(&path).unwrap();
        std::fs::remove_file(&path).unwrap();
        assert_eq!(&bytes[..8], b"\x89PNG\r\n\x1a\n");
        assert_eq!(&bytes[12..16], b"IHDR");
        assert_eq!(&bytes[16..24], &[0, 0, 0, 3, 0, 0, 0, 2]);
        // The stored block: two rows of a filter byte and nine of colour.
        let idat = bytes.windows(4).position(|w| w == b"IDAT").unwrap();
        assert_eq!(
            &bytes[idat + 4..idat + 11],
            &[0x78, 0x01, 1, 20, 0, 235, 255]
        );
        assert_eq!(
            &bytes[idat + 11..idat + 21],
            &[0, 255, 0, 0, 0, 255, 0, 0, 0, 255]
        );
        assert_eq!(&bytes[bytes.len() - 12..bytes.len() - 4], b"\0\0\0\0IEND");
        assert!(write_png(&path, 3, 2, &rgb[1..]).is_err());
    }

    #[test]
    fn options_come_in_pairs_and_unknown_ones_are_refused() {
        let parse = |args: &[&str]| Options::parse(args.iter().map(|arg| (*arg).to_owned()));
        let options = parse(&["--detail", "3", "--kernel", "sse2"]).unwrap();
        assert_eq!(options.number("detail", 0).unwrap(), 3);
        assert_eq!(options.number("passes", 7).unwrap(), 7);
        assert!(options.only(&["detail", "kernel"]).is_ok());
        assert!(options.only(&["detail"]).is_err());
        assert!(parse(&["--detail"]).is_err());
        assert!(parse(&["detail", "3"]).is_err());
        assert!(parse(&["--detail", "x"])
            .unwrap()
            .number("detail", 0u32)
            .is_err());
    }
}
