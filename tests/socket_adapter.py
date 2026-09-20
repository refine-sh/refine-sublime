"""Drive the production transport against the upstream real-socket fake peer."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from refine.protocol import Connection, Rejected, discover, make_store
from refine.validation import ConformanceError


def substitute(value, descriptor):
    if isinstance(value, str):
        return value.replace('${launchToken}', descriptor['launchToken']).replace('${serverEpoch}', descriptor['serverEpoch'])
    if isinstance(value, list):
        return [substitute(x, descriptor) for x in value]
    if isinstance(value, dict):
        return {key: substitute(x, descriptor) for key, x in value.items()}
    return value


def run(descriptor_path, scenario_id):
    root = Path(__file__).resolve().parents[1] / 'vendor/protocol'
    scenario = json.loads((root / 'vectors/state' / (scenario_id + '.json')).read_text())
    store = make_store()
    for transcript in scenario['connections']:
        descriptor = discover(store, descriptor_path)
        steps = transcript['steps']
        def message(step):
            return substitute(step.get('message', scenario.get('messages', {}).get(step.get('messageRef'))), descriptor)
        hello = message(steps[0])
        expected = message(steps[1])
        try:
            connection = Connection(store, descriptor, hello)
        except Rejected as error:
            assert error.message == expected
            continue
        except (ConformanceError, ValueError, UnicodeError):
            assert steps[1].get('invalid') or 'rawFrameHex' in steps[1]
            continue
        try:
            assert connection.welcome == expected
            starts = transcript.get('sequenceStarts', {})
            connection.command_sequence = starts.get('client', 1)
            connection.event_sequence = starts.get('server', 1)
            for step in steps[2:]:
                if step.get('close'):
                    if step['direction'] == 'client':
                        connection.close()
                    else:
                        try:
                            connection.receive()
                        except (EOFError, OSError):
                            pass
                        else:
                            raise AssertionError('Expected terminal close')
                    continue
                if step['direction'] == 'client':
                    connection.send_envelope(message(step))
                elif 'rawFrameHex' in step or step.get('invalid'):
                    try:
                        connection.receive()
                    except (ConformanceError, ValueError, UnicodeError, EOFError):
                        connection.close()
                    else:
                        raise AssertionError('Invalid frame accepted')
                else:
                    assert connection.receive() == message(step)
        finally:
            connection.close()
    print(json.dumps({'status': 'ok', 'scenario': scenario_id}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--descriptor', required=True)
    parser.add_argument('--scenario', required=True)
    args = parser.parse_args()
    run(args.descriptor, args.scenario)
