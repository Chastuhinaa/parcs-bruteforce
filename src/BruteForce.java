import java.io.*;
import java.security.MessageDigest;
import java.util.*;
import parcs.*;

public class BruteForce implements AM {

    String algo       = "SHA-256";
    String charset    = "abcdefghijklmnopqrstuvwxyz0123456789";
    int    length     = 5;
    String password   = "zzzzz";
    int[]  workers     = { 1, 2, 4, 8 };
    int    repeats     = 3;

    long   K;
    byte[] target;
    String targetHex;

    public static void main(String[] args) throws Exception {
        task curtask = new task();
        curtask.addJarFile("HashCrack.jar");

        BruteForce bf = new BruteForce();
        bf.loadConfig(curtask.findFile("input"));
        bf.target    = digest(bf.algo, bf.password.getBytes("US-ASCII"));
        bf.targetHex = toHex(bf.target);
        bf.K         = pow(bf.charset.length(), bf.length);

        bf.run(new AMInfo(curtask, (channel) null));
        curtask.end();
    }

    public void run(AMInfo info) {
        System.out.println("=== PARCS brute-force ===");
        System.out.println("algo=" + algo + "  charset.size=" + charset.length()
                + "  length=" + length + "  keyspace K=" + K);
        System.out.println("target(" + password + ") = " + targetHex);
        System.out.println();

        double seqBest = Double.MAX_VALUE;
        String seqPass = null;
        for (int r = 0; r < repeats; r++) {
            long t0 = System.nanoTime();
            long idx = scan(0, K);
            double sec = (System.nanoTime() - t0) / 1e9;
            seqPass = decode(idx);
            if (sec < seqBest) seqBest = sec;
            System.out.printf("sequential  run %d: %.2f s  found=%s%n", r + 1, sec, seqPass);
        }
        System.out.println();

        List<double[]> rows = new ArrayList<double[]>();
        for (int w : workers) {
            double best = Double.MAX_VALUE, sum = 0;
            boolean matchAll = true;
            for (int r = 0; r < repeats; r++) {
                long t0 = System.nanoTime();
                long idx = runParallel(info, w);
                double sec = (System.nanoTime() - t0) / 1e9;
                String pass = decode(idx);
                boolean ok = password.equals(pass);
                matchAll &= ok;
                sum += sec;
                if (sec < best) best = sec;
                System.out.printf("%d worker(s)  run %d: %.2f s  found=%s  match=%s%n",
                        w, r + 1, sec, pass, ok ? "yes" : "NO");
            }
            double avg = sum / repeats;
            rows.add(new double[]{ w, best, avg, seqBest / best, matchAll ? 1 : 0 });
        }

        printTable(seqBest, rows);
        writeCsv(info, seqBest, rows);
    }

    long runParallel(AMInfo info, int w) {
        point[]   p = new point[w];
        channel[] c = new channel[w];
        long chunk = K / w, rem = K % w, cur = 0;

        for (int i = 0; i < w; i++) {
            long len = chunk + (i < rem ? 1 : 0);
            long s = cur, e = cur + len;
            cur = e;
            p[i] = info.createPoint();
            c[i] = p[i].createChannel();
            p[i].execute("HashCrack");
            c[i].write((Serializable) algo);
            c[i].write((Serializable) charset);
            c[i].write(length);
            c[i].write((Serializable) targetHex);
            c[i].write(s);
            c[i].write(e);
        }

        long found = -1;
        for (int i = 0; i < w; i++) {
            long f = c[i].readLong();
            if (f >= 0) found = f;
        }
        return found;
    }

    long scan(long start, long end) {
        try {
            MessageDigest md = MessageDigest.getInstance(algo);
            int base = charset.length();
            byte[] alphabet = charset.getBytes("US-ASCII");
            byte[] cand = new byte[length];
            for (long idx = start; idx < end; idx++) {
                long x = idx;
                for (int pos = length - 1; pos >= 0; pos--) {
                    cand[pos] = alphabet[(int) (x % base)];
                    x /= base;
                }
                md.reset();
                md.update(cand, 0, length);
                if (Arrays.equals(md.digest(), target)) return idx;
            }
        } catch (Exception e) { e.printStackTrace(); }
        return -1L;
    }

    String decode(long idx) {
        if (idx < 0) return null;
        int base = charset.length();
        char[] buf = new char[length];
        long x = idx;
        for (int pos = length - 1; pos >= 0; pos--) {
            buf[pos] = charset.charAt((int) (x % base));
            x /= base;
        }
        return new String(buf);
    }

    void printTable(double seqBest, List<double[]> rows) {
        System.out.println();
        System.out.printf("Sequential baseline: %.2f s%n", seqBest);
        System.out.println("workers |  best, s | avg, s | speedup | efficiency | match");
        System.out.println("--------+----------+--------+---------+------------+------");
        for (double[] r : rows) {
            int w = (int) r[0];
            System.out.printf("%7d | %8.2f | %6.2f | %6.2fx | %9.1f%% | %s%n",
                    w, r[1], r[2], r[3], 100.0 * r[3] / w, r[4] == 1 ? "yes" : "NO");
        }
    }

    void writeCsv(AMInfo info, double seqBest, List<double[]> rows) {
        try {
            PrintWriter out = new PrintWriter(new FileWriter(info.curtask.addPath("results.csv")));
            out.println("workers,best_s,avg_s,speedup,efficiency_pct,match");
            out.printf(Locale.US, "0,%.3f,%.3f,1.000,100.0,yes%n", seqBest, seqBest);
            for (double[] r : rows) {
                int w = (int) r[0];
                out.printf(Locale.US, "%d,%.3f,%.3f,%.3f,%.1f,%s%n",
                        w, r[1], r[2], r[3], 100.0 * r[3] / w, r[4] == 1 ? "yes" : "no");
            }
            out.close();
            System.out.println("\nresults.csv written.");
        } catch (IOException e) { e.printStackTrace(); }
    }

    void loadConfig(String file) throws IOException {
        if (file == null) return;
        BufferedReader in = new BufferedReader(new FileReader(file));
        String line;
        while ((line = in.readLine()) != null) {
            line = line.trim();
            if (line.isEmpty() || line.startsWith("#")) continue;
            int eq = line.indexOf('=');
            if (eq < 0) continue;
            String k = line.substring(0, eq).trim();
            String v = line.substring(eq + 1).trim();
            if (k.equals("algo"))          algo = v;
            else if (k.equals("charset"))  charset = v;
            else if (k.equals("length"))   length = Integer.parseInt(v);
            else if (k.equals("password")) password = v;
            else if (k.equals("repeats"))  repeats = Integer.parseInt(v);
            else if (k.equals("workers")) {
                String[] parts = v.split("\\s+");
                workers = new int[parts.length];
                for (int i = 0; i < parts.length; i++) workers[i] = Integer.parseInt(parts[i]);
            }
        }
        in.close();
    }

    static byte[] digest(String algo, byte[] data) throws Exception {
        return MessageDigest.getInstance(algo).digest(data);
    }

    static String toHex(byte[] b) {
        StringBuilder sb = new StringBuilder();
        for (byte x : b) sb.append(String.format("%02x", x));
        return sb.toString();
    }

    static long pow(int base, int exp) {
        long r = 1;
        for (int i = 0; i < exp; i++) r *= base;
        return r;
    }
}
