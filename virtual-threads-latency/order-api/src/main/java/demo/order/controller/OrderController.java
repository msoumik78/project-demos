package demo.order.controller;

import demo.order.config.DownstreamProperties;
import demo.order.model.OrderResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrderController {

    private final RestClient downstream;
    private final DownstreamProperties properties;

    public OrderController(RestClient downstream, DownstreamProperties properties) {
        this.downstream = downstream;
        this.properties = properties;
    }

    @GetMapping("/orders/{id}")
    public OrderResponse order(@PathVariable String id) {
        downstream.get()
                .uri(uriBuilder -> uriBuilder
                        .path("/delay")
                        .queryParam("ms", properties.delayMs())
                        .queryParam("jitter", properties.jitterMs())
                        .build())
                .retrieve()
                .toBodilessEntity();
        return new OrderResponse(id, "FILLED");
    }
}
