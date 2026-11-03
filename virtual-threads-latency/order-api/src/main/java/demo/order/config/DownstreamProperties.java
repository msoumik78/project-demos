package demo.order.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "downstream")
public record DownstreamProperties(String baseUrl, int delayMs, int jitterMs) {
}
