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
        string python = FindPython(root);
        if (python == null)
        {
            MessageBox.Show(
                "找不到可用的 Python 3.12。\n\n请安装 Python 3.12，或补齐项目里的 .pylibs 后再试。",
                "Lumen View", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        var psi = new ProcessStartInfo
        {
            FileName = python,
            Arguments = "-m lumenview " + JoinArgs(args),
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

    private static string FindPython(string root)
    {
        string[] candidates =
        {
            Path.Combine(root, @".venv\Scripts\pythonw.exe"),
            Path.Combine(root, @"runtime\pythonw.exe"),
            @"C:\Users\zkang\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe"
        };
        foreach (string candidate in candidates)
        {
            if (File.Exists(candidate))
            {
                return candidate;
            }
        }

        string windir = Environment.GetEnvironmentVariable("WINDIR") ?? @"C:\Windows";
        string pyw = Path.Combine(windir, "pyw.exe");
        return File.Exists(pyw) ? pyw : null;
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
            sb.Append(arg.Replace("\"", "\\\""));
            sb.Append("\" ");
        }
        return sb.ToString();
    }
}
