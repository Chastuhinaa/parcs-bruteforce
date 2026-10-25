import parcs.*;
import java.security.MessageDigest;
import java.util.Arrays;

public class HashCrack implements AM {

    public void run(AMInfo info) {
        try {
            String algo      = (String) info.parent.readObject();
            String charset   = (String) info.parent.readObject();
            int    length    = info.parent.readInt();
            String targetHex = (String) info.parent.readObject();
            long   start     = info.parent.readLong();
            long   end       = info.parent.readLong();

            long found = crack(algo, charset, length, hexToBytes(targetHex), start, end);
            info.parent.write(found);
        } catch (Exception e) {
            e.printStackTrace();
            info.parent.write(-1L);
        }
    }

    static long crack(String algo, String charset, int length,
                      byte[] target, long start, long end) throws Exception {
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
            if (Arrays.equals(md.digest(), target)) {
                return idx;
            }
        }
        return -1L;
    }

    static byte[] hexToBytes(String s) {
        int n = s.length() / 2;
        byte[] b = new byte[n];
        for (int i = 0; i < n; i++) {
            b[i] = (byte) Integer.parseInt(s.substring(2 * i, 2 * i + 2), 16);
        }
        return b;
    }
}
