package demo.stub.controller;

import demo.stub.model.DelayResponse;
import java.util.concurrent.ThreadLocalRandom;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DelayController {

    @GetMapping("/delay")
    public DelayResponse delay(
            @RequestParam(name = "ms", defaultValue = "60") int ms,
            @RequestParam(name = "jitter", defaultValue = "0") int jitter) throws InterruptedException {
        int boundedMs = Math.max(0, ms);
        int boundedJitter = Math.max(0, jitter);
        int extra = boundedJitter == 0 ? 0 : ThreadLocalRandom.current().nextInt(boundedJitter + 1);
        int slept = boundedMs + extra;
        if (slept > 0) {
            Thread.sleep(slept);
        }
        return new DelayResponse(slept);
    }
}
