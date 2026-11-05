#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "UGAFTelemetryComponent.generated.h"

UCLASS(ClassGroup=(QA), meta=(BlueprintSpawnableComponent))
class UGAFTELEMETRY_API UUGAFTelemetryComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UUGAFTelemetryComponent();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="UGAF Telemetry")
    FString BridgeUrl = TEXT("http://127.0.0.1:8766/v1/events");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="UGAF Telemetry")
    FString Profile = TEXT("little-nightmares");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="UGAF Telemetry")
    FString BuildId = TEXT("development");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="UGAF Telemetry")
    FString SceneId = TEXT("unknown");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="UGAF Telemetry")
    FString ScenarioId = TEXT("steady-state");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="UGAF Telemetry")
    FString Phase = TEXT("steady");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="UGAF Telemetry", meta=(ClampMin="0.25", ClampMax="10.0"))
    float SampleIntervalSeconds = 1.0f;

    UFUNCTION(BlueprintCallable, Category="UGAF Telemetry")
    void SetScenario(const FString& NewScenarioId, const FString& NewPhase);

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:
    void SendSample();
    FString GetToken() const;
    TArray<float> FrameTimesMs;
    float ElapsedSeconds = 0.0f;
    int64 Sequence = 0;
};
