// Tiny launcher so Windows treats Lumen View as a real application.
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string prefix;
        string python = FindPython(root, out prefix);
        if (python == null)
        {
            MessageBox.Show(
                "找不到可用的 Python 3.12。\n\n请安装 64 位 Python 3.12，并运行 tools/fetch_libs.py 安装依赖。",
                "Lumen View", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        var psi = new ProcessStartInfo
        {
            FileName = python,
            Arguments = prefix + "-m lumenview " + JoinArgs(args),
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        psi.EnvironmentVariables["PYTHONPATH"] = root + ";" + Path.Combine(root, ".pylibs");
        psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";

        try
        {
            Process.Start(psi);
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show("启动失败：" + ex.Message, "Lumen View",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 2;
        }
    }

    private static string FindPython(string root, out string prefix)
    {
        string[] candidates = {
            Path.Combine(root, @".venv\Scripts\pythonw.exe"),
            Path.Combine(root, @"runtime\pythonw.exe"),
            "pyw.exe", "pythonw.exe"
        };
        foreach (string candidate in candidates)
        {
            string flags = candidate == "pyw.exe" ? "-3.12 " : "";
            try
            {
                var check = new ProcessStartInfo {
                    FileName = candidate,
                    Arguments = flags + "-c \"import sys; assert sys.version_info[:2] == (3,12) and sys.maxsize > 2**32; import PySide6, PIL\"",
                    WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true
                };
                check.EnvironmentVariables["PYTHONPATH"] = root + ";" + Path.Combine(root, ".pylibs");
                using (var process = Process.Start(check))
                {
                    if (!process.WaitForExit(10000)) { process.Kill(); continue; }
                    if (process.ExitCode == 0) { prefix = flags; return candidate; }
                }
            }
            catch { }
        }
        prefix = "";
        return null;
    }

    private static string JoinArgs(string[] args)
    {
        if (args == null || args.Length == 0)
        {
            return string.Empty;
        }
        var sb = new StringBuilder();
        foreach (string arg in args)
        {
            sb.Append('"');
            int slashes = 0;
            foreach (char c in arg)
            {
                if (c == '\\') { slashes++; continue; }
                sb.Append('\\', c == '"' ? slashes * 2 + 1 : slashes);
                sb.Append(c);
                slashes = 0;
            }
            sb.Append('\\', slashes * 2);
            sb.Append("\" ");
        }
        return sb.ToString();
    }
}
