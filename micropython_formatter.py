import datetime

def format_events_for_micropython(events):
    """
    Format unified events for MicroPython (e.g., OLED or serial display).
    This script can be uploaded to a MicroPython device or used by a 
    gateway to prepare data for one.
    """
    # Example format: [SubjectShort] HH:MM (Points)
    output = []
    for ev in events:
        # MicroPython might not have full strftime, so we use simple attributes
        dt = ev['start_dt']
        time_str = f"{dt.hour:02d}:{dt.minute:02d}"
        
        # Use a 4-letter subject code
        subject_code = ev['subject'][:4].upper()
        
        line = f"[{subject_code}] {time_str}"
        if ev['points'] > 0:
            line += f" ({ev['points']}p)"
            
        output.append(line)
        
    return "\n".join(output)
