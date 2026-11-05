#include "UGAFTelemetryComponent.h"

#include "Dom/JsonObject.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformMemory.h"

UUGAFTelemetryComponent::UUGAFTelemetryComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.TickGroup = TG_PostUpdateWork;
}

void UUGAFTelemetryComponent::BeginPlay()
{
    Super::BeginPlay();
    FrameTimesMs.Reset();
}

void UUGAFTelemetryComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    FrameTimesMs.Reset();
    Super::EndPlay(EndPlayReason);
}

void UUGAFTelemetryComponent::SetScenario(const FString& NewScenarioId, const FString& NewPhase)
{
    ScenarioId = NewScenarioId;
    Phase = NewPhase;
}

void UUGAFTelemetryComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
    if (DeltaTime > 0.0f && FMath::IsFinite(DeltaTime))
    {
        FrameTimesMs.Add(DeltaTime * 1000.0f);
    }
    ElapsedSeconds += DeltaTime;
    if (ElapsedSeconds >= FMath::Clamp(SampleIntervalSeconds, 0.25f, 10.0f) && FrameTimesMs.Num() > 0)
    {
        SendSample();
        ElapsedSeconds = 0.0f;
        FrameTimesMs.Reset();
    }
}

FString UUGAFTelemetryComponent::GetToken() const
{
    return FPlatformMisc::GetEnvironmentVariable(TEXT("UGAF_UNREAL_BRIDGE_TOKEN"));
}

void UUGAFTelemetryComponent::SendSample()
{
    const FString Token = GetToken();
    const bool bValidPhase = Phase == TEXT("warmup") || Phase == TEXT("steady") ||
        Phase == TEXT("spike") || Phase == TEXT("recovery") || Phase == TEXT("soak");
    if (Token.Len() < 24 || Profile.IsEmpty() || BuildId.IsEmpty() || BridgeUrl.IsEmpty() || !bValidPhase)
    {
        return;
    }

    TArray<float> Sorted = FrameTimesMs;
    Sorted.Sort();
    const int32 P95Index = FMath::Clamp(FMath::CeilToInt(static_cast<float>(Sorted.Num()) * 0.95f) - 1, 0, Sorted.Num() - 1);
    const double P95FrameMs = Sorted[P95Index];
    const TSharedRef<FJsonObject> AllowedMetrics = MakeShared<FJsonObject>();
    AllowedMetrics->SetNumberField(TEXT("frame_time_ms"), P95FrameMs);
    AllowedMetrics->SetNumberField(TEXT("fps"), P95FrameMs > 0.0 ? 1000.0 / P95FrameMs : 0.0);
    const FPlatformMemoryStats MemoryStats = FPlatformMemory::GetStats();
    AllowedMetrics->SetNumberField(
        TEXT("memory_mb"),
        static_cast<double>(MemoryStats.UsedPhysical) / (1024.0 * 1024.0)
    );

    const TSharedRef<FJsonObject> Performance = MakeShared<FJsonObject>();
    Performance->SetStringField(TEXT("scenario_id"), ScenarioId.IsEmpty() ? TEXT("steady-state") : ScenarioId);
    Performance->SetStringField(TEXT("phase"), Phase);
    Performance->SetObjectField(TEXT("metrics"), AllowedMetrics);

    const TSharedRef<FJsonObject> State = MakeShared<FJsonObject>();
    State->SetStringField(TEXT("scene_id"), SceneId.IsEmpty() ? TEXT("unknown") : SceneId);
    State->SetNumberField(TEXT("playback_seconds"), 0.0);
    State->SetObjectField(TEXT("performance"), Performance);

    const TSharedRef<FJsonObject> Event = MakeShared<FJsonObject>();
    Event->SetNumberField(TEXT("schema_version"), 1);
    Event->SetStringField(TEXT("profile"), Profile);
    Event->SetStringField(TEXT("build_id"), BuildId);
    Event->SetStringField(TEXT("event_id"), FGuid::NewGuid().ToString(EGuidFormats::DigitsWithHyphens));
    Event->SetNumberField(TEXT("sequence"), ++Sequence);
    Event->SetStringField(TEXT("emitted_at_utc"), FDateTime::UtcNow().ToIso8601());
    Event->SetStringField(TEXT("event_type"), TEXT("performance_sample"));
    Event->SetObjectField(TEXT("state"), State);

    FString Body;
    const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Body);
    if (!FJsonSerializer::Serialize(Event, Writer)) { return; }

    TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
    Request->SetURL(BridgeUrl);
    Request->SetVerb(TEXT("POST"));
    Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));
    Request->SetHeader(TEXT("Authorization"), FString::Printf(TEXT("Bearer %s"), *Token));
    Request->SetContentAsString(Body);
    Request->ProcessRequest();
}
