"""W2 ABI v1 reader for an explicitly paired, real PL observer GPIO.

This is not enabled by W1. No CPU medical processing or estimated core timing.
Use only from the single hardware worker, after DMA completion and before the
next frame. Caller validates the complete paired bit/HWH and official drivers.
"""

IDENTITY = 0x52513731
OBSERVER_ADDRESS = 0x41210000  # Validated W2 working BD; not an A4/W1 address.
UINT32 = 0xFFFFFFFF


def require(value, message):
    if not value:
        raise RuntimeError(message)


def control_word(*, side, stage, algorithm, threshold, tag):
    require(type(side) is int and side in (256, 512), 'Invalid image size')
    require(type(stage) is int and 0 <= stage <= 3, 'Invalid processing stage')
    require(algorithm in ('A', 'C2', 'C5', 'C7'), 'Invalid algorithm')
    require(type(threshold) is int and 1 <= threshold <= 255, 'Invalid PL threshold')
    require(type(tag) is int and 0 <= tag <= 0xFFFF, 'Invalid frame tag')
    return stage | (4 if side == 256 else 0) | ({'A':0,'C2':8,'C5':24,'C7':56}[algorithm]) | (threshold << 8) | (tag << 16)


def check_observer_metadata(description):
    require(description['type'] == 'xilinx.com:ip:axi_gpio:2.0' and
            description['phys_addr'] == OBSERVER_ADDRESS, 'Wrong W2 observer GPIO mapping')
    parameters = description['parameters']
    expected = {'C_IS_DUAL': 1, 'C_GPIO_WIDTH': 32, 'C_GPIO2_WIDTH': 32,
                'C_ALL_OUTPUTS': 1, 'C_ALL_INPUTS_2': 1, 'C_INTERRUPT_PRESENT': 0}
    require(all(int(parameters[name]) == value for name, value in expected.items()),
            'Wrong W2 observer GPIO parameters')


class QualityObserver:
    def __init__(self, gpio, *, verified_clock_hz):
        require(type(verified_clock_hz) is int and verified_clock_hz == 100_000_000,
                'Require the paired W2 100 MHz implementation; do not guess a clock')
        self.gpio = gpio
        self.clock_hz = verified_clock_hz
        gpio.channel1.setdirection('out')
        gpio.channel2.setdirection('in')
        require(self.read_word(0) == IDENTITY and self.read_word(12) == 32,
                'Wrong PL observer identity/counter width')

    def read_word(self, page):
        require(type(page) is int and 0 <= page <= 12, 'Invalid observer page')
        self.gpio.channel1.write(page, UINT32)
        value = int(self.gpio.channel2.read())
        require(0 <= value <= UINT32, 'Observer read outside uint32')
        return value

    def completed(self, *, expected_control, previous_sequence, expected_words):
        require(type(expected_control) is int and 0 <= expected_control <= UINT32 and
                expected_control & 0xC0 == 0 and (not expected_control & 16 or expected_control & 8) and
                (not expected_control & 32 or expected_control & 24 == 24) and (expected_control >> 8) & 255,
                'Invalid expected frame control')
        require(type(previous_sequence) is int and 0 <= previous_sequence <= UINT32,
                'Invalid previous frame sequence')
        words = 65536 if expected_control & 4 else 262144
        require(type(expected_words) is int and expected_words == words, 'Wrong expected frame length')
        # A read spanning two completions must never mix their timing/parameters.
        for _ in range(3):
            before = self.read_word(4)
            pages = {page: self.read_word(page) for page in (1, 3, 5, 6, 7, 8, 9, 10, 11)}
            after = self.read_word(4)
            if before == after:
                break
        else:
            raise RuntimeError('Observer snapshot changed repeatedly; preserve hardware state')
        require(pages[1] == 2, 'Observer is busy, invalid, rejected, overflowing or has unknown flags')
        require(after == ((previous_sequence + 1) & UINT32) and pages[11] == after,
                'Observer frame sequence does not match the completed task')
        require(pages[3] == expected_control, 'Hardware latched parameters do not match this task')
        require(pages[9] == words and pages[10] == words, 'Wrong actual core input/output word count')
        core, drain, gaps, stalls = (pages[page] for page in (5, 6, 7, 8))
        require(words - 1 <= core <= drain and gaps <= core and drain - core <= stalls <= drain,
                'Inconsistent raw hardware cycle boundaries')
        pages[4] = after
        return {'abi': 'W2_RQ71_V1', 'sequence': after, 'latched_control': pages[3],
                'task_tag': pages[3] >> 16, 'raw_pages': {str(k): v for k, v in pages.items()},
                'clock_hz_from_paired_implementation': self.clock_hz,
                'pl_core_cycles': core, 'pl_drain_cycles': drain,
                'pl_input_empty_cycles': gaps, 'pl_output_backpressure_cycles': stalls,
                'pl_core_frame_ns': core * 1_000_000_000 // self.clock_hz,
                'pl_drain_ns': drain * 1_000_000_000 // self.clock_hz,
                'core_boundary': 'First HLS input handshake to final HLS output first valid',
                'core_includes_stream_stalls': True, 'pure_dma_transport_ns': None}
