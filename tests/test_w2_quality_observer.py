"""Host-only observer protocol failures; simulated GPIO never becomes board evidence."""
import unittest
from pynq_app.quality_observer import (QualityObserver, control_word, check_observer_metadata,
                                       IDENTITY, OBSERVER_ADDRESS, UINT32)


class GPIO:
    def __init__(self, pages):
        self.pages = dict(pages)
        self.page = 0
        self.channel1 = self.Output(self)
        self.channel2 = self.Input(self)
        self.sequence_reads = []

    class Output:
        def __init__(self, owner): self.owner = owner
        def setdirection(self, direction): assert direction == 'out'
        def write(self, page, mask):
            assert mask == UINT32
            self.owner.page = page

    class Input:
        def __init__(self, owner): self.owner = owner
        def setdirection(self, direction): assert direction == 'in'
        def read(self):
            o = self.owner
            if o.page == 4 and o.sequence_reads:
                return o.sequence_reads.pop(0)
            return o.pages[o.page]


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.control = control_word(side=256, stage=3, algorithm='C2', threshold=28, tag=0xBEEF)
        self.gpio = GPIO({0: IDENTITY, 1: 2, 3: self.control, 4: 7, 5: 91747, 6: 91811,
                          7: 970, 8: 21747, 9: 65536, 10: 65536, 11: 7, 12: 32})
        self.reader = QualityObserver(self.gpio, verified_clock_hz=100_000_000)

    def read(self, previous=6):
        return self.reader.completed(expected_control=self.control, previous_sequence=previous, expected_words=65536)

    def test_exact_hardware_snapshot_and_ns(self):
        result = self.read()
        self.assertEqual(result['latched_control'], 0xBEEF1C0F)
        self.assertEqual(result['pl_core_frame_ns'], 917470)
        self.assertEqual(result['pl_drain_ns'], 918110)
        self.assertIsNone(result['pure_dma_transport_ns'])
        self.assertTrue(result['core_includes_stream_stalls'])

    def test_dynamic_control_edges_and_invalid_inputs(self):
        for t in (1, 27, 28, 29, 255):
            for algorithm in ('A', 'C2'):
                word = control_word(side=512, stage=0, algorithm=algorithm, threshold=t, tag=65535)
                self.assertEqual((word >> 8) & 255, t)
                self.assertEqual((word >> 3) & 1, algorithm == 'C2')
                self.assertEqual(word & 0xF4, 0)
        for key, value in [('side', 128), ('stage', 4), ('algorithm', 'B'), ('threshold', 0),
                           ('threshold', 256), ('threshold', True), ('tag', -1), ('tag', 65536)]:
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                args = dict(side=256, stage=3, algorithm='C2', threshold=28, tag=0)
                args[key] = value
                control_word(**args)

    def test_all_nonready_or_overflow_flags_rejected(self):
        for flags in (0, 1, 3, 6, 10, 18):
            with self.subTest(flags=flags), self.assertRaises(RuntimeError):
                self.gpio.pages[1] = flags
                self.read()

    def test_stale_wrong_tag_or_word_counts_rejected(self):
        for page, value in [(3, self.control ^ 0x10000), (3, self.control ^ 0x100), (4, 6),
                            (9, 65535), (10, 65535), (11, 8)]:
            old = self.gpio.pages[page]
            with self.subTest(page=page), self.assertRaises(RuntimeError):
                self.gpio.pages[page] = value
                self.read()
            self.gpio.pages[page] = old

    def test_torn_snapshot_retried_but_not_merged(self):
        self.gpio.sequence_reads = [6, 7, 7, 7]
        self.assertEqual(self.read()['sequence'], 7)

    def test_unstable_snapshot_bounded_failure(self):
        self.gpio.sequence_reads = [1, 2, 3, 4, 5, 6]
        with self.assertRaisesRegex(RuntimeError, 'changed repeatedly'):
            self.read()
        self.assertEqual(self.gpio.sequence_reads, [])

    def test_sequence_wrap_is_explicit(self):
        self.gpio.pages[4] = self.gpio.pages[11] = 0
        self.assertEqual(self.read(previous=UINT32)['sequence'], 0)

    def test_inconsistent_cycle_windows_rejected(self):
        for page, value in [(5, 1), (5, 91812), (6, 91746), (7, 91748), (8, 63), (8, 91812)]:
            old = self.gpio.pages[page]
            with self.subTest(page=page, value=value), self.assertRaises(RuntimeError):
                self.gpio.pages[page] = value
                self.read()
            self.gpio.pages[page] = old

    def test_wrong_identity_counter_width_and_clock_rejected(self):
        for page, value in [(0, 0), (12, 8)]:
            old = self.gpio.pages[page]
            with self.assertRaises(RuntimeError):
                self.gpio.pages[page] = value
                QualityObserver(self.gpio, verified_clock_hz=100_000_000)
            self.gpio.pages[page] = old
        with self.assertRaises(RuntimeError):
            QualityObserver(self.gpio, verified_clock_hz=50_000_000)

    def test_hwh_identity_and_official_gpio_shape_required(self):
        d = {'type': 'xilinx.com:ip:axi_gpio:2.0', 'phys_addr': OBSERVER_ADDRESS,
             'parameters': dict(C_IS_DUAL='1', C_GPIO_WIDTH='32', C_GPIO2_WIDTH='32',
                                C_ALL_OUTPUTS='1', C_ALL_INPUTS_2='1', C_INTERRUPT_PRESENT='0')}
        check_observer_metadata(d)
        d['phys_addr'] = 0x41200000
        with self.assertRaises(RuntimeError): check_observer_metadata(d)
        d['phys_addr'] = OBSERVER_ADDRESS
        d['parameters']['C_IS_DUAL'] = '0'
        with self.assertRaises(RuntimeError): check_observer_metadata(d)


if __name__ == '__main__':
    unittest.main()
