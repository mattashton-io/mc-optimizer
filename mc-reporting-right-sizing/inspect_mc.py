from google.cloud import migrationcenter_v1
import proto

def find_utilization_fields():
    for name in dir(migrationcenter_v1):
        cls = getattr(migrationcenter_v1, name)
        if isinstance(cls, type) and issubclass(cls, proto.Message):
            # check fields of this message
            for field_name in cls.meta.fields:
                if any(x in field_name.lower() for x in ["utilization", "cpu", "memory", "disk"]):
                    print(f"Message {name} has field {field_name}")

if __name__ == "__main__":
    find_utilization_fields()
