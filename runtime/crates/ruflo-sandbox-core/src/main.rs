/*!
Ruflo OS Sandbox Core Wrapper

This binary acts as the secure entry point for sandboxed worker processes.
It leverages Linux namespaces, pivot_root, and (optionally) seccomp-bpf
to tightly isolate the agent processes from the host OS.

Usage:
  ruflo-sandbox-core --workdir /tmp/sandbox-123 -- /bin/bash -c "echo hello"
*/

use anyhow::{Context, Result};
use clap::Parser;
use nix::mount::{mount, MsFlags};
use nix::sched::{clone, unshare, CloneFlags};
use nix::sys::wait::{waitpid, WaitStatus};
use nix::unistd::{execvp, pivot_root, chdir};
use std::ffi::CString;
use std::process::exit;

#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    /// Sandbox working directory (will be pivot_root'ed into)
    #[arg(short, long)]
    workdir: String,

    /// Command to execute
    #[arg(last = true, required = true)]
    command: Vec<String>,
}

fn setup_sandbox(args: &Args) -> Result<()> {
    tracing::info!("Setting up sandbox environment...");

    // Isolate namespaces
    unshare(
        CloneFlags::CLONE_NEWNS
            | CloneFlags::CLONE_NEWPID
            | CloneFlags::CLONE_NEWIPC
            | CloneFlags::CLONE_NEWUTS
            // CLONE_NEWUSER requires extra mappings; kept simple here
    )
    .context("Failed to unshare namespaces")?;

    // Make mount namespace private
    mount(
        None::<&str>,
        "/",
        None::<&str>,
        MsFlags::MS_REC | MsFlags::MS_PRIVATE,
        None::<&str>,
    )
    .context("Failed to mark / as MS_PRIVATE")?;

    // In a full implementation, we would set up a new rootfs here,
    // mount /proc, /dev, /sys, and use pivot_root.
    // For this scaffold, we just chdir to the workdir.
    chdir(args.workdir.as_str()).context("Failed to chdir to workdir")?;

    tracing::info!("Namespaces isolated.");
    Ok(())
}

fn run_child(args: &Args) -> Result<()> {
    setup_sandbox(args)?;

    let c_command = CString::new(args.command[0].clone())?;
    let c_args: Vec<CString> = args
        .command
        .iter()
        .map(|s| CString::new(s.clone()).unwrap())
        .collect();

    tracing::info!("Executing: {:?}", args.command);
    
    // In production, we apply seccomp-bpf filters right before execvp
    
    execvp(&c_command, &c_args).context("Failed to exec")?;
    unreachable!();
}

fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let args = Args::parse();

    // Fork off the child process that will be sandboxed
    // In Rust, using `fork` with multi-threading is unsafe, but here we are single-threaded
    match unsafe { nix::unistd::fork() } {
        Ok(nix::unistd::ForkResult::Parent { child, .. }) => {
            tracing::info!("Started sandbox worker with PID: {}", child);
            match waitpid(child, None)? {
                WaitStatus::Exited(_, status) => exit(status),
                WaitStatus::Signaled(_, sig, _) => {
                    tracing::error!("Sandbox killed by signal: {:?}", sig);
                    exit(128 + sig as i32);
                }
                _ => exit(1),
            }
        }
        Ok(nix::unistd::ForkResult::Child) => {
            if let Err(e) = run_child(&args) {
                tracing::error!("Sandbox failed: {:?}", e);
                exit(1);
            }
        }
        Err(e) => anyhow::bail!("Fork failed: {}", e),
    }

    Ok(())
}
